import asyncio
import motor.motor_asyncio
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://bijay:bijay@bot.eczw2nh.mongodb.net/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
OWNER_ID = int(os.getenv("OWNER_ID", "1192694890530869369"))
MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "1348916338961154088"))
MAIN_SERVER_INVITE = os.getenv("MAIN_SERVER_INVITE", "https://discord.gg/WVq522fsr3")

class DatabaseSetup:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        
    async def setup_collections(self):
        print(f"Setting up database: {DATABASE_NAME}")
        
        collections = await self.db.list_collection_names()
        
        required_collections = ["users", "servers", "config", "statistics"]
        for collection in required_collections:
            if collection not in collections:
                await self.db.create_collection(collection)
                print(f"Created collection: {collection}")
            else:
                print(f"Collection already exists: {collection}")
        
        await self.create_indexes()
        await self.initialize_config()
        await self.initialize_statistics()
        
    async def create_indexes(self):
        print("\nCreating indexes...")
        
        await self.db.users.create_index("user_id", unique=True)
        print("Created unique index on users.user_id")
        
        await self.db.servers.create_index("server_id", unique=True)
        print("Created unique index on servers.server_id")
        
        await self.db.users.create_index("last_active")
        print("Created index on users.last_active")
        
        await self.db.users.create_index("blacklisted")
        print("Created index on users.blacklisted")
        
    async def initialize_config(self):
        print("\nInitializing bot configuration...")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        
        if not config:
            config_doc = {
                "_id": "bot_config",
                "owner_id": OWNER_ID,
                "main_server_id": MAIN_SERVER_ID,
                "main_server_invite": MAIN_SERVER_INVITE,
                "main_log_channel": None,
                "feedback_minutes": 15,
                "point_rates": {
                    "daily": 2,
                    "invite": 2
                },
                "blacklist_days": 30,
                "maintenance_mode": False
            }
            
            await self.db.config.insert_one(config_doc)
            print("Created bot configuration")
        else:
            print("Bot configuration already exists")
            
    async def initialize_statistics(self):
        print("\nInitializing statistics tracking...")
        
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        
        if not stats:
            cookie_types = ["netflix", "spotify", "prime", "jiohotstar", 
                          "tradingview", "chatgpt", "claude", "peacock", "crunchyroll", "canalplus"]
            
            weekly_stats = {cookie: 0 for cookie in cookie_types}
            total_stats = {cookie: 0 for cookie in cookie_types}
            
            stats_doc = {
                "_id": "global_stats",
                "weekly_claims": weekly_stats,
                "total_claims": total_stats,
                "week_start": datetime.now(timezone.utc),
                "last_reset": datetime.now(timezone.utc),
                "all_time_users": 0,
                "all_time_claims": 0
            }
            
            await self.db.statistics.insert_one(stats_doc)
            print("Created statistics tracking")
        else:
            print("Statistics tracking already exists")
            
        weekly_stats = await self.db.statistics.find_one({"_id": "weekly_stats"})
        if not weekly_stats:
            cookie_types = ["netflix", "spotify", "prime", "jiohotstar", 
                          "tradingview", "chatgpt", "claude", "peacock", "crunchyroll", "canalplus"]
            current_week = datetime.now(timezone.utc).isocalendar()[1]
            weekly_doc = {
                "_id": "weekly_stats",
                "week_number": current_week,
                "year": datetime.now(timezone.utc).year,
                "claims_by_type": {cookie: 0 for cookie in cookie_types},
                "claims_by_day": {},
                "unique_users": [],
                "week_start": datetime.now(timezone.utc)
            }
            await self.db.statistics.insert_one(weekly_doc)
            print("Created weekly statistics")
            
    async def setup_default_configs(self):
        print("\nSetting up default configurations...")
        
        base_dir = "D:/Discord Bot/cookies"
        default_cookies = {
            "netflix": {"cost": 5, "cooldown": 72, "directory": f"{base_dir}/netflix", "enabled": True},
            "spotify": {"cost": 3, "cooldown": 48, "directory": f"{base_dir}/spotify", "enabled": True},
            "prime": {"cost": 4, "cooldown": 72, "directory": f"{base_dir}/prime", "enabled": True},
            "jiohotstar": {"cost": 3, "cooldown": 48, "directory": f"{base_dir}/jiohotstar", "enabled": True},
            "tradingview": {"cost": 8, "cooldown": 96, "directory": f"{base_dir}/tradingview", "enabled": True},
            "chatgpt": {"cost": 10, "cooldown": 96, "directory": f"{base_dir}/chatgpt", "enabled": True},
            "claude": {"cost": 12, "cooldown": 120, "directory": f"{base_dir}/claude", "enabled": True},
            "peacock": {"cost": 4, "cooldown": 72, "directory": f"{base_dir}/peacock", "enabled": True},
            "crunchyroll": {"cost": 4, "cooldown": 48, "directory": f"{base_dir}/crunchyroll", "enabled": True},
            "canalplus": {"cost": 6, "cooldown": 72, "directory": f"{base_dir}/canalplus", "enabled": True}
        }
        
        default_roles = {
            "free": {"name": "Free", "cooldown": 72, "cost": "default", "access": ["netflix", "spotify", "prime"]},
            "premium": {"name": "Premium", "cooldown": 24, "cost": 2, "access": ["all"]},
            "booster": {"name": "Booster", "cooldown": 6, "cost": 0, "access": ["all"]},
            "inviter": {"name": "Inviter", "cooldown": 48, "cost": 3, "access": ["all"]},
            "vip": {"name": "VIP", "cooldown": 12, "cost": 0, "access": ["all"]},
            "staff": {"name": "Staff", "cooldown": 0, "cost": 0, "access": ["all"]}
        }
        
        await self.db.config.update_one(
            {"_id": "bot_config"},
            {"$set": {
                "default_cookies": default_cookies,
                "default_roles": default_roles,
                "default_channels": ["cookie", "feedback", "log", "announcement"]
            }}
        )
        print("Default configurations saved")
        
    async def smart_server_setup(self):
        print("\nChecking for existing Discord servers...")
        
        servers_updated = 0
        
        async for server in self.db.servers.find():
            server_id = server.get("server_id")
            
            if not server.get("cookies"):
                config = await self.db.config.find_one({"_id": "bot_config"})
                await self.db.servers.update_one(
                    {"server_id": server_id},
                    {"$set": {"cookies": config["default_cookies"]}}
                )
                servers_updated += 1
                print(f"Updated server {server_id} with default cookies")
                
            if not server.get("role_based"):
                await self.db.servers.update_one(
                    {"server_id": server_id},
                    {"$set": {"role_based": True}}
                )
                servers_updated += 1
                
        print(f"Servers updated: {servers_updated}")
            
    async def check_and_fix_database(self):
        print("\n=== Database Health Check ===")
        
        issues_fixed = 0
        
        async for user in self.db.users.find():
            if "points" not in user:
                await self.db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"points": 0}}
                )
                issues_fixed += 1
                
            if "blacklisted" not in user:
                await self.db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"blacklisted": False, "blacklist_expires": None}}
                )
                issues_fixed += 1
                
        async for server in self.db.servers.find():
            if "role_based" not in server:
                await self.db.servers.update_one(
                    {"_id": server["_id"]},
                    {"$set": {"role_based": True}}
                )
                issues_fixed += 1
                
        print(f"Issues fixed: {issues_fixed}")
        
    async def create_sample_data(self):
        print("\n=== Creating Sample Data ===")
        
        sample_users = [
            {
                "user_id": 111111111, 
                "username": "test_user1", 
                "points": 50, 
                "trust_score": 75,
                "cookie_claims": {
                    "netflix": 5,
                    "spotify": 3,
                    "prime": 2
                },
                "weekly_claims": 10,
                "total_claims": 10
            },
            {
                "user_id": 222222222, 
                "username": "test_user2", 
                "points": 100, 
                "trust_score": 90,
                "cookie_claims": {},
                "weekly_claims": 0,
                "total_claims": 0
            },
            {
                "user_id": 333333333, 
                "username": "test_user3", 
                "points": 0, 
                "trust_score": 50,
                "cookie_claims": {},
                "weekly_claims": 0,
                "total_claims": 0
            }
        ]
        
        for user_data in sample_users:
            user_data.update({
                "total_earned": user_data["points"],
                "total_spent": 0,
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "daily_claimed": None,
                "invite_count": 0,
                "last_claim": None,
                "blacklisted": False,
                "blacklist_expires": None
            })
            
            existing = await self.db.users.find_one({"user_id": user_data["user_id"]})
            if not existing:
                await self.db.users.insert_one(user_data)
                print(f"Created sample user: {user_data['username']}")
                
    async def show_stats(self):
        print("\n=== Database Statistics ===")
        
        users_count = await self.db.users.count_documents({})
        servers_count = await self.db.servers.count_documents({})
        blacklisted_count = await self.db.users.count_documents({"blacklisted": True})
        
        print(f"Total users: {users_count}")
        print(f"Total servers: {servers_count}")
        print(f"Blacklisted users: {blacklisted_count}")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config:
            print(f"Bot owner ID: {config['owner_id']}")
            print(f"Maintenance mode: {config['maintenance_mode']}")
            print(f"Cookie types configured: {len(config.get('default_cookies', {}))}")
            
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        if stats:
            print(f"\n=== Cookie Statistics ===")
            print(f"All-time claims: {stats.get('all_time_claims', 0)}")
            top_cookies = sorted(stats.get('total_claims', {}).items(), key=lambda x: x[1], reverse=True)[:5]
            if top_cookies:
                print("Top 5 cookies:")
                for cookie, count in top_cookies:
                    print(f"  {cookie}: {count} claims")
                    
    async def run(self):
        try:
            print("🚀 Smart Database Setup Starting...")
            print("=" * 50)
            await self.client.admin.command('ping')
            print("✅ Successfully connected to MongoDB!")
            
            await self.setup_collections()
            await self.setup_default_configs()
            await self.smart_server_setup()
            await self.check_and_fix_database()
            await self.create_sample_data()
            await self.show_stats()
            
            print("\n✅ Database setup completed successfully!")
            print("=" * 50)
            
        except Exception as e:
            print(f"\n❌ Error during setup: {e}")
        finally:
            self.client.close()
            print("\nDatabase connection closed.")

async def main():
    setup = DatabaseSetup()
    await setup.run()

if __name__ == "__main__":
    asyncio.run(main())