from datetime import datetime, timezone
import logging

logger = logging.getLogger('CookieBot')

class DatabaseHandler:
    def __init__(self, bot):
        self.bot = bot
        
    async def initialize_database(self):
        collections = ['users', 'servers', 'config', 'statistics', 'feedback', 'analytics']
        existing = await self.bot.db.list_collection_names()
        
        for collection in collections:
            if collection not in existing:
                await self.bot.db.create_collection(collection)
                print(f"📂 Created collection: {collection}")
        
        indexes = {
            'users': [
                {'keys': [('user_id', 1)], 'unique': True},
                {'keys': [('points', -1)], 'unique': False},
                {'keys': [('trust_score', -1)], 'unique': False}
            ],
            'servers': [
                {'keys': [('server_id', 1)], 'unique': True}
            ],
            'feedback': [
                {'keys': [('user_id', 1)], 'unique': False},
                {'keys': [('timestamp', -1)], 'unique': False}
            ]
        }
        
        for collection, index_list in indexes.items():
            try:
                existing_indexes = await self.bot.db[collection].list_indexes().to_list(None)
                existing_names = {idx['name'] for idx in existing_indexes}
                
                for index_config in index_list:
                    index_name = '_'.join([f"{k}_{v}" for k, v in index_config['keys']])
                    
                    if index_name not in existing_names:
                        await self.bot.db[collection].create_index(
                            index_config['keys'],
                            unique=index_config.get('unique', False)
                        )
                        print(f"📑 Created index {index_name} on {collection}")
                    else:
                        print(f"✓ Index {index_name} already exists on {collection}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not create indexes for {collection}: {e}")
                print(f"⚠️ Could not create indexes for {collection}: {e}")
        
        config = await self.bot.db.config.find_one({"_id": "bot_config"})
        if not config:
            await self.bot.db.config.insert_one({
                "_id": "bot_config",
                "maintenance_mode": False,
                "feedback_minutes": 15,
                "version": "2.0.0",
                "created_at": datetime.now(timezone.utc)
            })
        
        stats = await self.bot.db.statistics.find_one({"_id": "global_stats"})
        if not stats:
            await self.bot.db.statistics.insert_one({
                "_id": "global_stats",
                "total_claims": {},
                "weekly_claims": {},
                "all_time_claims": 0,
                "created_at": datetime.now(timezone.utc)
            })