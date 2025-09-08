# bot_core/database.py
# Fixed database handler with correct MongoDB admin command syntax

from datetime import datetime, timezone
import logging
import asyncio
import motor.motor_asyncio
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError, ConnectionFailure
import os

logger = logging.getLogger('CookieBot')

class DatabaseHandler:
    def __init__(self, bot):
        self.bot = bot
        self._connection_retries = 0
        self._max_retries = 3
        self._retry_delay = 1
        self._last_ping = datetime.now(timezone.utc)
        
    async def ensure_connection(self):
        """Ensure MongoDB connection is alive"""
        try:
            # Only ping if more than 5 seconds since last ping
            now = datetime.now(timezone.utc)
            if (now - self._last_ping).total_seconds() < 5:
                return True
                
            await asyncio.wait_for(
                self.bot.mongo_client.admin.command('ping'),
                timeout=2.0
            )
            self._last_ping = now
            self._connection_retries = 0
            return True
        except (asyncio.TimeoutError, ConnectionFailure, ServerSelectionTimeoutError):
            logger.warning("MongoDB connection lost, reconnecting...")
            return await self._reconnect()
        except Exception as e:
            # Ignore SSL errors - they're transient
            if "SSL" in str(e) or "10054" in str(e):
                return True  # Connection is actually fine
            logger.warning(f"MongoDB connection check failed: {e}")
            return True  # Assume connection is OK
    
    async def _reconnect(self):
        """Reconnect to MongoDB"""
        if self._connection_retries >= self._max_retries:
            logger.error("Max reconnection attempts reached")
            return False
            
        self._connection_retries += 1
        delay = self._retry_delay * self._connection_retries
        
        logger.info(f"Reconnecting to MongoDB (attempt {self._connection_retries}/{self._max_retries})...")
        await asyncio.sleep(delay)
        
        try:
            # Don't create new client, just test existing one
            await asyncio.wait_for(
                self.bot.mongo_client.admin.command('ping'),
                timeout=5.0
            )
            logger.info("MongoDB reconnection successful")
            self._connection_retries = 0
            self._last_ping = datetime.now(timezone.utc)
            return True
            
        except Exception as e:
            logger.error(f"MongoDB reconnection failed: {e}")
            return False
    
    async def safe_db_operation(self, operation, *args, **kwargs):
        """Execute database operation with automatic retry"""
        last_error = None
        
        for attempt in range(3):
            try:
                # For cursor operations, don't check connection
                if hasattr(operation, '__name__') and 'find' in operation.__name__:
                    return operation(*args, **kwargs)
                
                # For write operations, execute directly
                result = await operation(*args, **kwargs)
                return result
                
            except (AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError, ConnectionFailure) as e:
                last_error = e
                logger.warning(f"Database operation failed (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    # Try to ensure connection for next attempt
                    await self.ensure_connection()
                    
            except Exception as e:
                # Ignore SSL and connection reset errors
                if "SSL" in str(e) or "10054" in str(e) or "10053" in str(e):
                    await asyncio.sleep(0.5)
                    continue
                logger.error(f"Unexpected database error: {e}")
                raise
                
        # If all attempts failed, raise the last error
        if last_error:
            raise last_error
    
    async def initialize_database(self):
        try:
            # Create collections if they don't exist
            collections = ['users', 'servers', 'config', 'statistics', 'feedback', 'analytics']
            existing = await self.bot.db.list_collection_names()
            
            for collection in collections:
                if collection not in existing:
                    await self.bot.db.create_collection(collection)
                    print(f"📂 Created: {collection}")
            
            # Create critical indexes only
            critical_indexes = {
                'users': [('user_id', 1)],
                'servers': [('server_id', 1)]
            }
            
            for collection, index in critical_indexes.items():
                try:
                    await self.bot.db[collection].create_index(
                        index,
                        unique=True,
                        background=True
                    )
                except Exception as e:
                    if "already exists" not in str(e):
                        logger.warning(f"Index creation warning for {collection}: {e}")
            
            # Initialize config if needed
            config = await self.bot.db.config.find_one({"_id": "bot_config"})
            if not config:
                await self.bot.db.config.insert_one({
                    "_id": "bot_config",
                    "maintenance_mode": False,
                    "feedback_minutes": 15,
                    "version": "2.0.0",
                    "created_at": datetime.now(timezone.utc)
                })
            
            # Initialize stats if needed
            stats = await self.bot.db.statistics.find_one({"_id": "global_stats"})
            if not stats:
                await self.bot.db.statistics.insert_one({
                    "_id": "global_stats",
                    "total_claims": {},
                    "weekly_claims": {},
                    "all_time_claims": 0,
                    "created_at": datetime.now(timezone.utc)
                })
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            # Don't raise - let the bot continue