import asyncio
import motor.motor_asyncio
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv('setup/.env')

class EnhancedDatabaseSetup:
    def __init__(self):
        self.MONGODB_URI = os.getenv("MONGODB_URI")
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
        self.OWNER_ID = int(os.getenv("OWNER_ID", "1192694890530869369"))
        self.MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "1348916338961154088"))
        self.MAIN_SERVER_INVITE = os.getenv("MAIN_SERVER_INVITE", "https://discord.gg/WVq522fsr3")
        
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.MONGODB_URI)
        self.db = self.client[self.DATABASE_NAME]
        
    async def setup_collections(self):
        print(f"🔧 Setting up database: {self.DATABASE_NAME}")
        print("=" * 50)
        
        collections = await self.db.list_collection_names()
        
        required_collections = [
            "users", "servers", "config", "statistics", 
            "feedback", "analytics", "blacklist_appeals", 
            "cookie_logs", "transactions", "warnings"
        ]
        
        for collection in required_collections:
            if collection not in collections:
                await self.db.create_collection(collection)
                print(f"✅ Created collection: {collection}")
            else:
                print(f"✓ Collection exists: {collection}")
        
        await self.create_enhanced_indexes()
        await self.initialize_bot_config()
        await self.initialize_statistics()
        await self.initialize_analytics()
        await self.setup_cookie_tracking()
        
    async def create_enhanced_indexes(self):
        print("\n📑 Creating optimized indexes...")
        
        indexes = {
            'users': [
                {'keys': [('user_id', 1)], 'unique': True},
                {'keys': [('points', -1)], 'unique': False},
                {'keys': [('trust_score', -1)], 'unique': False},
                {'keys': [('total_claims', -1)], 'unique': False},
                {'keys': [('blacklisted', 1)], 'unique': False},
                {'keys': [('last_active', -1)], 'unique': False},
                {'keys': [('invite_count', -1)], 'unique': False}
            ],
            'servers': [
                {'keys': [('server_id', 1)], 'unique': True},
                {'keys': [('enabled', 1)], 'unique': False},
                {'keys': [('premium_tier', 1)], 'unique': False}
            ],
            'feedback': [
                {'keys': [('user_id', 1)], 'unique': False},
                {'keys': [('timestamp', -1)], 'unique': False},
                {'keys': [('cookie_type', 1)], 'unique': False},
                {'keys': [('rating', -1)], 'unique': False}
            ],
            'cookie_logs': [
                {'keys': [('user_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('server_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('cookie_type', 1, 'timestamp', -1)], 'unique': False}
            ],
            'transactions': [
                {'keys': [('user_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('type', 1)], 'unique': False}
            ]
        }
        
        for collection, index_list in indexes.items():
            try:
                existing_indexes = await self.db[collection].list_indexes().to_list(None)
                existing_names = {idx['name'] for idx in existing_indexes}
                
                for index_config in index_list:
                    index_name = '_'.join([f"{k}_{v}" for k, v in index_config['keys']])
                    
                    if index_name not in existing_names:
                        await self.db[collection].create_index(
                            index_config['keys'],
                            unique=index_config.get('unique', False)
                        )
                        print(f"✅ Created index {index_name} on {collection}")
                    else:
                        print(f"✓ Index {index_name} exists on {collection}")
                        
            except Exception as e:
                print(f"⚠️ Could not create indexes for {collection}: {e}")
        
    async def initialize_bot_config(self):
        print("\n⚙️ Initializing bot configuration...")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        
        config_doc = {
            "_id": "bot_config",
            "owner_id": self.OWNER_ID,
            "main_server_id": self.MAIN_SERVER_ID,
            "main_server_invite": self.MAIN_SERVER_INVITE,
            "main_log_channel": None,
            "error_webhook": None,
            "analytics_webhook": None,
            "feedback_minutes": 15,
            "maintenance_mode": False,
            "version": "2.0.0",
            "features": {
                "auto_blacklist": True,
                "role_based_system": True,
                "analytics_tracking": True,
                "premium_features": True,
                "invite_tracking": True,
                "auto_directory_creation": True
            },
            "point_rates": {
                "daily": 2,
                "invite": 2,
                "boost": 50,
                "vote": 5,
                "feedback_bonus": 1,
                "perfect_rating_bonus": 2
            },
            "cooldown_settings": {
                "daily_hours": 24,
                "feedback_minutes": 15,
                "blacklist_days": 30
            },
            "premium_tiers": {
                "basic": {
                    "name": "Basic",
                    "max_servers": 5,
                    "custom_cookies": False,
                    "advanced_analytics": False
                },
                "pro": {
                    "name": "Pro",
                    "max_servers": 20,
                    "custom_cookies": True,
                    "advanced_analytics": True
                },
                "enterprise": {
                    "name": "Enterprise",
                    "max_servers": -1,
                    "custom_cookies": True,
                    "advanced_analytics": True,
                    "priority_support": True
                }
            },
            "default_cookies": self.get_default_cookies(),
            "default_roles": self.get_default_roles(),
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc)
        }
        
        if not config:
            await self.db.config.insert_one(config_doc)
            print("✅ Created bot configuration")
        else:
            await self.db.config.update_one(
                {"_id": "bot_config"},
                {"$set": {
                    "version": "2.0.0",
                    "features": config_doc["features"],
                    "premium_tiers": config_doc["premium_tiers"],
                    "last_updated": datetime.now(timezone.utc)
                }}
            )
            print("✅ Updated bot configuration")
            
    def get_default_cookies(self):
        base_dir = "cookies"
        return {
            "netflix": {
                "cost": 5, 
                "cooldown": 72, 
                "directory": f"{base_dir}/netflix", 
                "enabled": True,
                "description": "Premium Netflix accounts",
                "emoji": "🎬",
                "category": "streaming"
            },
            "spotify": {
                "cost": 3, 
                "cooldown": 48, 
                "directory": f"{base_dir}/spotify", 
                "enabled": True,
                "description": "Premium Spotify accounts",
                "emoji": "🎵",
                "category": "music"
            },
            "prime": {
                "cost": 4, 
                "cooldown": 72, 
                "directory": f"{base_dir}/prime", 
                "enabled": True,
                "description": "Amazon Prime accounts",
                "emoji": "📦",
                "category": "streaming"
            },
            "jiohotstar": {
                "cost": 3, 
                "cooldown": 48, 
                "directory": f"{base_dir}/jiohotstar", 
                "enabled": True,
                "description": "JioHotstar Premium accounts",
                "emoji": "⭐",
                "category": "streaming"
            },
            "tradingview": {
                "cost": 8, 
                "cooldown": 96, 
                "directory": f"{base_dir}/tradingview", 
                "enabled": True,
                "description": "TradingView Pro accounts",
                "emoji": "📈",
                "category": "tools"
            },
            "chatgpt": {
                "cost": 10, 
                "cooldown": 96, 
                "directory": f"{base_dir}/chatgpt", 
                "enabled": True,
                "description": "ChatGPT Plus accounts",
                "emoji": "🤖",
                "category": "ai"
            },
            "claude": {
                "cost": 12, 
                "cooldown": 120, 
                "directory": f"{base_dir}/claude", 
                "enabled": True,
                "description": "Claude Pro accounts",
                "emoji": "🧠",
                "category": "ai"
            },
            "peacock": {
                "cost": 4, 
                "cooldown": 72, 
                "directory": f"{base_dir}/peacock", 
                "enabled": True,
                "description": "Peacock Premium accounts",
                "emoji": "🦚",
                "category": "streaming"
            },
            "crunchyroll": {
                "cost": 4, 
                "cooldown": 48, 
                "directory": f"{base_dir}/crunchyroll", 
                "enabled": True,
                "description": "Crunchyroll Premium accounts",
                "emoji": "🍙",
                "category": "anime"
            },
            "canalplus": {
                "cost": 6, 
                "cooldown": 72, 
                "directory": f"{base_dir}/canalplus", 
                "enabled": True,
                "description": "Canal+ Premium accounts",
                "emoji": "📺",
                "category": "streaming"
            }
        }
    
    def get_default_roles(self):
        return {
            "free": {
                "name": "Free",
                "cooldown": 72,
                "cost": "default",
                "access": ["netflix", "spotify", "prime"],
                "daily_bonus": 0,
                "trust_multiplier": 1.0
            },
            "premium": {
                "name": "Premium",
                "cooldown": 24,
                "cost": 2,
                "access": ["all"],
                "daily_bonus": 5,
                "trust_multiplier": 1.5
            },
            "vip": {
                "name": "VIP",
                "cooldown": 12,
                "cost": 1,
                "access": ["all"],
                "daily_bonus": 10,
                "trust_multiplier": 2.0
            },
            "elite": {
                "name": "Elite",
                "cooldown": 6,
                "cost": 0,
                "access": ["all"],
                "daily_bonus": 20,
                "trust_multiplier": 2.5
            },
            "booster": {
                "name": "Booster",
                "cooldown": 0,
                "cost": 0,
                "access": ["all"],
                "daily_bonus": 50,
                "trust_multiplier": 3.0
            },
            "staff": {
                "name": "Staff",
                "cooldown": 0,
                "cost": 0,
                "access": ["all"],
                "daily_bonus": 100,
                "trust_multiplier": 5.0
            }
        }
    
    async def initialize_statistics(self):
        print("\n📊 Initializing statistics tracking...")
        
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        
        if not stats:
            cookie_types = list(self.get_default_cookies().keys())
            
            stats_doc = {
                "_id": "global_stats",
                "total_claims": {cookie: 0 for cookie in cookie_types},
                "weekly_claims": {cookie: 0 for cookie in cookie_types},
                "monthly_claims": {cookie: 0 for cookie in cookie_types},
                "all_time_claims": 0,
                "total_users": 0,
                "total_servers": 0,
                "total_points_distributed": 0,
                "total_blacklists": 0,
                "created_at": datetime.now(timezone.utc),
                "last_reset": datetime.now(timezone.utc)
            }
            
            await self.db.statistics.insert_one(stats_doc)
            print("✅ Created global statistics")
        else:
            print("✓ Statistics tracking exists")
    
    async def initialize_analytics(self):
        print("\n📈 Initializing analytics collection...")
        
        analytics_docs = [
            {
                "_id": "bot_analytics",
                "total_users": 0,
                "total_servers": 0,
                "total_commands": 0,
                "total_cookies": 0,
                "total_transactions": 0,
                "average_trust_score": 50,
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "command_usage",
                "commands": {
                    cmd: {
                        "total": 0,
                        "today": 0,
                        "this_week": 0,
                        "this_month": 0,
                        "unique_users": [],
                        "guilds": [],
                        "average_execution_time": 0
                    } for cmd in ["cookie", "daily", "points", "help", "stock", 
                                  "feedback", "invites", "status", "leaderboard", 
                                  "refresh", "analytics"]
                },
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "cookie_performance",
                "cookies": {
                    cookie: {
                        "total_claims": 0,
                        "successful_claims": 0,
                        "failed_claims": 0,
                        "average_rating": 0,
                        "feedback_count": 0,
                        "blacklist_rate": 0,
                        "stock_alerts": 0
                    } for cookie in self.get_default_cookies().keys()
                },
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "user_behavior",
                "average_session_length": 0,
                "retention_rate": {
                    "daily": 0,
                    "weekly": 0,
                    "monthly": 0
                },
                "churn_rate": 0,
                "engagement_metrics": {
                    "commands_per_user": 0,
                    "claims_per_user": 0,
                    "feedback_rate": 0
                },
                "last_updated": datetime.now(timezone.utc)
            }
        ]
        
        for doc in analytics_docs:
            existing = await self.db.analytics.find_one({"_id": doc["_id"]})
            if not existing:
                await self.db.analytics.insert_one(doc)
                print(f"✅ Created {doc['_id']} analytics")
            else:
                print(f"✓ {doc['_id']} analytics exists")
    
    async def setup_cookie_tracking(self):
        print("\n🍪 Setting up cookie tracking system...")
        
        tracking_doc = await self.db.config.find_one({"_id": "cookie_tracking"})
        
        if not tracking_doc:
            tracking = {
                "_id": "cookie_tracking",
                "file_tracking": {},
                "distribution_history": [],
                "stock_thresholds": {
                    "critical": 5,
                    "low": 10,
                    "medium": 20,
                    "good": 50
                },
                "auto_restock": {
                    "enabled": False,
                    "sources": [],
                    "check_interval": 3600
                },
                "quality_control": {
                    "enabled": True,
                    "min_rating": 3.0,
                    "blacklist_threshold": 5
                },
                "created_at": datetime.now(timezone.utc)
            }
            
            await self.db.config.insert_one(tracking)
            print("✅ Created cookie tracking system")
        else:
            print("✓ Cookie tracking exists")
    
    async def create_directories(self):
        print("\n📁 Creating cookie directories...")
        
        base_dir = Path("cookies")
        base_dir.mkdir(exist_ok=True)
        
        cookies = self.get_default_cookies()
        for cookie_type, config in cookies.items():
            cookie_dir = Path(config["directory"])
            cookie_dir.mkdir(parents=True, exist_ok=True)
            
            readme_path = cookie_dir / "README.txt"
            if not readme_path.exists():
                readme_content = f"""Cookie Directory: {cookie_type.upper()}
=================================
Place .txt files containing cookies here.
Each file should contain one cookie per line.

Format examples:
- email:password
- username:password
- token
- session_id

Files will be randomly selected and distributed.
"""
                readme_path.write_text(readme_content)
            
            print(f"✅ Created directory: {cookie_dir}")
    
    async def setup_sample_data(self):
        print("\n📝 Creating sample data...")
        
        sample_server = {
            "server_id": 999999999,
            "server_name": "Test Server",
            "enabled": True,
            "setup_complete": True,
            "channels": {
                "cookie": None,
                "feedback": None,
                "log": None,
                "announcement": None
            },
            "cookies": self.get_default_cookies(),
            "role_based": True,
            "roles": {},
            "settings": {
                "feedback_required": True,
                "feedback_timeout": 15,
                "max_daily_claims": 10,
                "blacklist_after_warnings": 3
            },
            "created_at": datetime.now(timezone.utc)
        }
        
        existing = await self.db.servers.find_one({"server_id": sample_server["server_id"]})
        if not existing:
            await self.db.servers.insert_one(sample_server)
            print("✅ Created sample server")
        
        sample_users = [
            {
                "user_id": 111111111,
                "username": "test_user1",
                "points": 50,
                "total_earned": 50,
                "total_spent": 0,
                "trust_score": 75,
                "cookie_claims": {"netflix": 5, "spotify": 3},
                "total_claims": 8,
                "weekly_claims": 8,
                "daily_claimed": None,
                "invite_count": 5,
                "blacklisted": False
            },
            {
                "user_id": 222222222,
                "username": "premium_user",
                "points": 100,
                "total_earned": 150,
                "total_spent": 50,
                "trust_score": 90,
                "cookie_claims": {"chatgpt": 2, "claude": 1},
                "total_claims": 3,
                "weekly_claims": 3,
                "daily_claimed": None,
                "invite_count": 10,
                "blacklisted": False
            }
        ]
        
        for user_data in sample_users:
            user_data.update({
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "blacklist_expires": None,
                "preferences": {
                    "dm_notifications": True,
                    "claim_confirmations": True,
                    "feedback_reminders": True
                },
                "statistics": {
                    "feedback_streak": 0,
                    "perfect_ratings": 0,
                    "favorite_cookie": None
                }
            })
            
            existing = await self.db.users.find_one({"user_id": user_data["user_id"]})
            if not existing:
                await self.db.users.insert_one(user_data)
                print(f"✅ Created sample user: {user_data['username']}")
    
    async def verify_setup(self):
        print("\n✅ Verifying setup...")
        
        collections = await self.db.list_collection_names()
        config = await self.db.config.find_one({"_id": "bot_config"})
        
        checks = {
            "Collections": len(collections),
            "Configuration": "✅" if config else "❌",
            "Cookie Types": len(config.get("default_cookies", {})) if config else 0,
            "Role Types": len(config.get("default_roles", {})) if config else 0,
            "Users": await self.db.users.count_documents({}),
            "Servers": await self.db.servers.count_documents({})
        }
        
        print("\n📋 Setup Verification:")
        for item, value in checks.items():
            print(f"  {item}: {value}")
    
    async def show_summary(self):
        print("\n" + "=" * 50)
        print("📊 DATABASE SETUP SUMMARY")
        print("=" * 50)
        
        stats = {
            "Total Collections": len(await self.db.list_collection_names()),
            "Total Users": await self.db.users.count_documents({}),
            "Total Servers": await self.db.servers.count_documents({}),
            "Blacklisted Users": await self.db.users.count_documents({"blacklisted": True}),
            "Total Feedback": await self.db.feedback.count_documents({})
        }
        
        for key, value in stats.items():
            print(f"{key}: {value}")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config:
            print(f"\nBot Version: {config.get('version', 'Unknown')}")
            print(f"Owner ID: {config.get('owner_id')}")
            print(f"Maintenance Mode: {config.get('maintenance_mode', False)}")
    
    async def run(self):
        try:
            print("🚀 Enhanced Database Setup Starting...")
            print("=" * 50)
            
            await self.client.admin.command('ping')
            print("✅ Successfully connected to MongoDB!\n")
            
            await self.setup_collections()
            await self.create_directories()
            await self.setup_sample_data()
            await self.verify_setup()
            await self.show_summary()
            
            print("\n✅ Enhanced database setup completed successfully!")
            print("=" * 50)
            
        except Exception as e:
            print(f"\n❌ Error during setup: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.client.close()
            print("\n🔌 Database connection closed.")

async def main():
    setup = EnhancedDatabaseSetup()
    await setup.run()

if __name__ == "__main__":
    asyncio.run(main())