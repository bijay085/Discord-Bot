# bot_core/database.py
# Fixed database handler with correct MongoDB admin command syntax

from datetime import datetime, timezone
import logging
import asyncio
import motor.motor_asyncio
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError
import os

logger = logging.getLogger('CookieBot')

class DatabaseHandler:
    def __init__(self, bot):
        self.bot = bot
        self._connection_retries = 0
        self._max_retries = 3
        self._retry_delay = 1
        
    async def ensure_connection(self):
        """Ensure MongoDB connection is alive, reconnect if needed"""
        try:
            # Correct syntax for motor admin command
            await self.bot.mongo_client.admin.command('ping')
            self._connection_retries = 0  # Reset on success
            return True
        except Exception as e:
            logger.warning(f"MongoDB connection check failed: {e}")
            return await self._reconnect()
    
    async def _reconnect(self):
        """Attempt to reconnect to MongoDB with exponential backoff"""
        if self._connection_retries >= self._max_retries:
            logger.error("Max reconnection attempts reached")
            return False
            
        self._connection_retries += 1
        delay = self._retry_delay * (2 ** (self._connection_retries - 1))
        
        logger.info(f"Attempting MongoDB reconnection {self._connection_retries}/{self._max_retries} in {delay}s...")
        await asyncio.sleep(delay)
        
        try:
            # Close existing connection
            if self.bot.mongo_client:
                self.bot.mongo_client.close()
            
            # Create new connection with optimized settings
            MONGODB_URI = os.getenv("MONGODB_URI")
            DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
            
            self.bot.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                maxPoolSize=20,
                minPoolSize=5,
                maxIdleTimeMS=30000,
                waitQueueTimeoutMS=5000,
                serverSelectionTimeoutMS=5000,  # Increased for DNS issues
                connectTimeoutMS=10000,  # Increased for DNS issues
                retryWrites=True,
                retryReads=True,
                w=1,
                readPreference='primaryPreferred',
                heartbeatFrequencyMS=10000,
                socketTimeoutMS=30000,
                # DNS resolution settings
                directConnection=False,
                dns_resolver='pymongo'
            )
            
            self.bot.db = self.bot.mongo_client[DATABASE_NAME]
            
            # Test connection with correct syntax
            await self.bot.mongo_client.admin.command('ping')
            logger.info("MongoDB reconnection successful")
            self._connection_retries = 0
            return True
            
        except Exception as e:
            logger.error(f"MongoDB reconnection failed: {e}")
            return False
    
    async def safe_db_operation(self, operation, *args, **kwargs):
        """Execute database operation with automatic retry on connection failure"""
        for attempt in range(3):
            try:
                # For find operations that return cursors
                if hasattr(operation, '__name__') and 'find' in operation.__name__:
                    # Don't check connection for cursor operations
                    result = operation(*args, **kwargs)
                    return result
                
                # For other operations, ensure connection first
                if not await self.ensure_connection():
                    raise ConnectionError("MongoDB connection unavailable")
                
                # Execute the operation
                result = await operation(*args, **kwargs)
                return result
                
            except (AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError) as e:
                logger.warning(f"Database operation failed (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    raise
            except ConnectionError:
                # Try to reconnect once more
                if attempt < 2 and await self._reconnect():
                    continue
                raise
            except Exception as e:
                logger.error(f"Unexpected database error: {e}")
                raise
    
    async def initialize_database(self):
        try:
            # Use the client's list_database_names instead of db.list_collection_names for initial check
            await self.safe_db_operation(self.bot.mongo_client.list_database_names)
            
            collections = ['users', 'servers', 'config', 'statistics', 'feedback', 'analytics']
            existing = await self.bot.db.list_collection_names()
            
            for collection in collections:
                if collection not in existing:
                    await self.bot.db.create_collection(collection)
                    print(f"📂 Created: {collection}")
            
            # Create indexes with error handling
            indexes = {
                'users': [
                    {'keys': [('user_id', 1)], 'unique': True},
                    {'keys': [('points', -1)], 'unique': False},
                    {'keys': [('trust_score', -1)], 'unique': False},
                    {'keys': [('last_active', -1)], 'unique': False}
                ],
                'servers': [
                    {'keys': [('server_id', 1)], 'unique': True},
                    {'keys': [('enabled', 1)], 'unique': False}
                ],
                'feedback': [
                    {'keys': [('user_id', 1)], 'unique': False},
                    {'keys': [('timestamp', -1)], 'unique': False}
                ]
            }
            
            for collection, index_list in indexes.items():
                try:
                    # Get existing indexes
                    existing_indexes = []
                    async for idx in self.bot.db[collection].list_indexes():
                        existing_indexes.append(idx)
                    
                    existing_names = {idx['name'] for idx in existing_indexes}
                    
                    for index_config in index_list:
                        index_name = '_'.join([f"{k}_{v}" for k, v in index_config['keys']])
                        
                        if index_name not in existing_names:
                            try:
                                await self.bot.db[collection].create_index(
                                    index_config['keys'],
                                    unique=index_config.get('unique', False),
                                    background=True
                                )
                                print(f"📑 Index created: {index_name}")
                            except Exception as e:
                                if "already exists" not in str(e):
                                    logger.warning(f"⚠️ Index creation failed for {collection}: {e}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Index error for {collection}: {e}")
            
            # Initialize config
            config = await self.bot.db.config.find_one({"_id": "bot_config"})
            
            if not config:
                await self.bot.db.config.insert_one({
                    "_id": "bot_config",
                    "maintenance_mode": False,
                    "feedback_minutes": 15,
                    "version": "2.0.0",
                    "created_at": datetime.now(timezone.utc)
                })
            
            # Initialize stats
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
            raise