# bot_core/database.py
# Enhanced database handler with connection retry logic and better error handling

from datetime import datetime, timezone
import logging
import asyncio
import os
import motor.motor_asyncio
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError

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
            # Quick ping to check connection
            await self.bot.db.admin.command('ping')
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
                maxPoolSize=20,  # Reduced from 40
                minPoolSize=5,   # Reduced from 7
                maxIdleTimeMS=30000,  # Reduced from 45000
                waitQueueTimeoutMS=5000,  # Reduced from 10000
                serverSelectionTimeoutMS=3000,  # Reduced from 5000
                connectTimeoutMS=5000,  # Reduced from 10000
                retryWrites=True,
                retryReads=True,
                w=1,  # Changed from 'majority' for faster writes
                readPreference='primaryPreferred',  # Changed from 'nearest'
                heartbeatFrequencyMS=10000,  # More frequent heartbeats
                socketTimeoutMS=30000
            )
            
            self.bot.db = self.bot.mongo_client[DATABASE_NAME]
            
            # Test connection
            await self.bot.db.admin.command('ping')
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
                # Ensure connection before operation
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
            except Exception as e:
                logger.error(f"Unexpected database error: {e}")
                raise
    
    async def initialize_database(self):
        collections = ['users', 'servers', 'config', 'statistics', 'feedback', 'analytics']
        existing = await self.safe_db_operation(self.bot.db.list_collection_names)
        
        for collection in collections:
            if collection not in existing:
                await self.safe_db_operation(self.bot.db.create_collection, collection)
                print(f"📂 Created: {collection}")
        
        # Create indexes with error handling
        indexes = {
            'users': [
                {'keys': [('user_id', 1)], 'unique': True},
                {'keys': [('points', -1)], 'unique': False},
                {'keys': [('trust_score', -1)], 'unique': False},
                {'keys': [('last_active', -1)], 'unique': False}  # Index for cleanup
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
                existing_indexes = await self.safe_db_operation(
                    self.bot.db[collection].list_indexes().to_list, None
                )
                existing_names = {idx['name'] for idx in existing_indexes}
                
                for index_config in index_list:
                    index_name = '_'.join([f"{k}_{v}" for k, v in index_config['keys']])
                    
                    if index_name not in existing_names:
                        try:
                            await self.safe_db_operation(
                                self.bot.db[collection].create_index,
                                index_config['keys'],
                                unique=index_config.get('unique', False),
                                background=True  # Non-blocking index creation
                            )
                            print(f"📑 Index created: {index_name}")
                        except Exception as e:
                            if "already exists" not in str(e):
                                logger.warning(f"⚠️ Index creation failed for {collection}: {e}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Index error for {collection}: {e}")
        
        # Initialize config with safe operation
        config = await self.safe_db_operation(
            self.bot.db.config.find_one, {"_id": "bot_config"}
        )
        
        if not config:
            await self.safe_db_operation(
                self.bot.db.config.insert_one,
                {
                    "_id": "bot_config",
                    "maintenance_mode": False,
                    "feedback_minutes": 15,
                    "version": "2.0.0",
                    "created_at": datetime.now(timezone.utc)
                }
            )
        
        # Initialize stats with safe operation
        stats = await self.safe_db_operation(
            self.bot.db.statistics.find_one, {"_id": "global_stats"}
        )
        
        if not stats:
            await self.safe_db_operation(
                self.bot.db.statistics.insert_one,
                {
                    "_id": "global_stats",
                    "total_claims": {},
                    "weekly_claims": {},
                    "all_time_claims": 0,
                    "created_at": datetime.now(timezone.utc)
                }
            )