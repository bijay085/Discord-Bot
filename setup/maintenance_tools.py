import asyncio
import motor.motor_asyncio
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
from pathlib import Path
import shutil
import json
from typing import Dict, List, Optional

load_dotenv('setup/.env')

class BotMaintenanceTools:
    def __init__(self):
        self.MONGODB_URI = os.getenv("MONGODB_URI")
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.MONGODB_URI)
        self.db = self.client[self.DATABASE_NAME]
        
    async def backup_database(self, backup_dir: str = "backups"):
        """Create a complete backup of the database"""
        print("📦 Starting database backup...")
        
        backup_path = Path(backup_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path.mkdir(parents=True, exist_ok=True)
        
        collections = await self.db.list_collection_names()
        
        for collection in collections:
            print(f"  Backing up {collection}...")
            data = await self.db[collection].find().to_list(None)
            
            with open(backup_path / f"{collection}.json", 'w') as f:
                json.dump(data, f, default=str, indent=2)
        
        print(f"✅ Backup completed: {backup_path}")
        return backup_path
    
    async def restore_database(self, backup_path: str):
        """Restore database from backup"""
        print("📥 Starting database restore...")
        
        backup_dir = Path(backup_path)
        if not backup_dir.exists():
            print("❌ Backup directory not found!")
            return False
        
        for json_file in backup_dir.glob("*.json"):
            collection_name = json_file.stem
            print(f"  Restoring {collection_name}...")
            
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            if data:
                await self.db[collection_name].delete_many({})
                await self.db[collection_name].insert_many(data)
        
        print("✅ Restore completed!")
        return True
    
    async def clean_inactive_users(self, days: int = 90):
        """Remove users who haven't been active for X days"""
        print(f"🧹 Cleaning users inactive for {days} days...")
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        result = await self.db.users.delete_many({
            "last_active": {"$lt": cutoff_date},
            "total_claims": 0,
            "points": {"$lt": 10}
        })
        
        print(f"✅ Removed {result.deleted_count} inactive users")
        return result.deleted_count
    
    async def reset_weekly_stats(self):
        """Reset weekly statistics"""
        print("📊 Resetting weekly statistics...")
        
        await self.db.users.update_many(
            {},
            {"$set": {"weekly_claims": 0}}
        )
        
        await self.db.statistics.update_one(
            {"_id": "global_stats"},
            {
                "$set": {
                    "weekly_claims": {},
                    "week_start": datetime.now(timezone.utc)
                }
            }
        )
        
        await self.db.analytics.update_many(
            {},
            {
                "$set": {
                    "commands.$[].this_week": 0,
                    "cookies.$[].this_week": 0,
                    "total_this_week": 0,
                    "weekly_active_users": []
                }
            }
        )
        
        print("✅ Weekly stats reset completed")
    
    async def migrate_data(self):
        """Migrate data to new schema"""
        print("🔄 Starting data migration...")
        
        migrations_performed = 0
        
        async for user in self.db.users.find():
            updates = {}
            
            if "preferences" not in user:
                updates["preferences"] = {
                    "dm_notifications": True,
                    "claim_confirmations": True,
                    "feedback_reminders": True
                }
                
            if "statistics" not in user:
                updates["statistics"] = {
                    "feedback_streak": 0,
                    "perfect_ratings": 0,
                    "favorite_cookie": None
                }
            
            if "invited_users" not in user:
                updates["invited_users"] = []
                updates["pending_invites"] = 0
                updates["verified_invites"] = 0
                updates["fake_invites"] = 0
            
            if updates:
                await self.db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": updates}
                )
                migrations_performed += 1
        
        async for server in self.db.servers.find():
            updates = {}
            
            if "settings" not in server:
                updates["settings"] = {
                    "feedback_required": True,
                    "feedback_timeout": 15,
                    "max_daily_claims": 10,
                    "blacklist_after_warnings": 3,
                    "invite_tracking": True,
                    "analytics_enabled": True
                }
            
            if "premium_tier" not in server:
                updates["premium_tier"] = "basic"
            
            if "setup_complete" not in server:
                updates["setup_complete"] = server.get("enabled", False)
            
            if updates:
                await self.db.servers.update_one(
                    {"_id": server["_id"]},
                    {"$set": updates}
                )
                migrations_performed += 1
        
        print(f"✅ Migration completed: {migrations_performed} documents updated")
    
    async def fix_corrupted_data(self):
        """Fix common data corruption issues"""
        print("🔧 Fixing corrupted data...")
        
        fixes = 0
        
        async for user in self.db.users.find():
            updates = {}
            
            if not isinstance(user.get("points"), (int, float)) or user.get("points") < 0:
                updates["points"] = 0
                
            if not isinstance(user.get("trust_score"), (int, float)):
                updates["trust_score"] = 50
            elif user.get("trust_score") > 100:
                updates["trust_score"] = 100
            elif user.get("trust_score") < 0:
                updates["trust_score"] = 0
            
            if user.get("blacklisted") and not user.get("blacklist_expires"):
                updates["blacklist_expires"] = datetime.now(timezone.utc) + timedelta(days=30)
            
            if updates:
                await self.db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": updates}
                )
                fixes += 1
        
        result = await self.db.users.update_many(
            {"last_active": {"$type": "string"}},
            [{"$set": {"last_active": {"$dateFromString": {"dateString": "$last_active"}}}}]
        )
        fixes += result.modified_count
        
        print(f"✅ Fixed {fixes} data issues")
    
    async def optimize_performance(self):
        """Optimize database performance"""
        print("⚡ Optimizing database performance...")
        
        await self.db.users.delete_many({"user_id": {"$exists": False}})
        
        await self.db.feedback.delete_many({
            "timestamp": {"$lt": datetime.now(timezone.utc) - timedelta(days=90)}
        })
        
        await self.db.analytics.delete_many({
            "timestamp": {"$lt": datetime.now(timezone.utc) - timedelta(days=30)}
        })
        
        collections = await self.db.list_collection_names()
        for collection in collections:
            await self.db.command("compact", collection)
        
        print("✅ Performance optimization completed")
    
    async def generate_analytics_report(self):
        """Generate comprehensive analytics report"""
        print("📊 Generating analytics report...")
        
        report = {
            "generated_at": datetime.now(timezone.utc),
            "database": self.DATABASE_NAME,
            "statistics": {}
        }
        
        report["statistics"]["total_users"] = await self.db.users.count_documents({})
        report["statistics"]["active_users"] = await self.db.users.count_documents({
            "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)}
        })
        report["statistics"]["blacklisted_users"] = await self.db.users.count_documents({"blacklisted": True})
        report["statistics"]["total_servers"] = await self.db.servers.count_documents({})
        report["statistics"]["enabled_servers"] = await self.db.servers.count_documents({"enabled": True})
        
        points_agg = await self.db.users.aggregate([
            {
                "$group": {
                    "_id": None,
                    "total_points": {"$sum": "$points"},
                    "avg_points": {"$avg": "$points"},
                    "total_earned": {"$sum": "$total_earned"},
                    "total_spent": {"$sum": "$total_spent"}
                }
            }
        ]).to_list(1)
        
        if points_agg:
            report["statistics"]["economy"] = points_agg[0]
            del report["statistics"]["economy"]["_id"]
        
        cookie_stats = await self.db.statistics.find_one({"_id": "global_stats"})
        if cookie_stats:
            report["statistics"]["cookie_claims"] = {
                "all_time": cookie_stats.get("all_time_claims", 0),
                "by_type": cookie_stats.get("total_claims", {})
            }
        
        feedback_stats = await self.db.feedback.aggregate([
            {
                "$group": {
                    "_id": "$cookie_type",
                    "count": {"$sum": 1},
                    "avg_rating": {"$avg": "$rating"}
                }
            }
        ]).to_list(None)
        
        if feedback_stats:
            report["statistics"]["feedback"] = {
                item["_id"]: {
                    "count": item["count"],
                    "avg_rating": round(item.get("avg_rating", 0), 2)
                }
                for item in feedback_stats if item["_id"]
            }
        
        report_path = Path("reports") / f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(exist_ok=True)
        
        with open(report_path, 'w') as f:
            json.dump(report, f, default=str, indent=2)
        
        print(f"✅ Report saved to: {report_path}")
        return report
    
    async def check_directory_stock(self):
        """Check cookie directory stock levels"""
        print("📦 Checking cookie stock levels...")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if not config:
            print("❌ Bot config not found!")
            return
        
        stock_report = {}
        low_stock_alerts = []
        
        for cookie_type, cookie_config in config.get("default_cookies", {}).items():
            directory = Path(cookie_config["directory"])
            
            if directory.exists():
                files = list(directory.glob("*.txt"))
                stock_count = len(files)
                
                stock_report[cookie_type] = {
                    "directory": str(directory),
                    "stock": stock_count,
                    "status": self._get_stock_status(stock_count)
                }
                
                if stock_count < 10:
                    low_stock_alerts.append(f"{cookie_type}: {stock_count} files")
            else:
                stock_report[cookie_type] = {
                    "directory": str(directory),
                    "stock": 0,
                    "status": "❌ Directory Missing"
                }
                directory.mkdir(parents=True, exist_ok=True)
        
        print("\n📊 Stock Report:")
        for cookie, info in stock_report.items():
            print(f"  {cookie}: {info['stock']} files - {info['status']}")
        
        if low_stock_alerts:
            print(f"\n⚠️ Low Stock Alerts: {', '.join(low_stock_alerts)}")
        
        return stock_report
    
    def _get_stock_status(self, count: int) -> str:
        if count == 0:
            return "❌ Out of Stock"
        elif count < 5:
            return "🔴 Critical"
        elif count < 10:
            return "🟠 Low"
        elif count < 20:
            return "🟡 Medium"
        else:
            return "🟢 Good"
    
    async def export_user_data(self, user_id: int):
        """Export all data for a specific user (GDPR compliance)"""
        print(f"📤 Exporting data for user {user_id}...")
        
        user_data = {
            "export_date": datetime.now(timezone.utc),
            "user_id": user_id
        }
        
        user_data["profile"] = await self.db.users.find_one({"user_id": user_id})
        
        user_data["feedback"] = await self.db.feedback.find({"user_id": user_id}).to_list(None)
        
        user_data["transactions"] = await self.db.transactions.find({"user_id": user_id}).to_list(None)
        
        user_data["cookie_logs"] = await self.db.cookie_logs.find({"user_id": user_id}).to_list(None)
        
        export_path = Path("exports") / f"user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        export_path.parent.mkdir(exist_ok=True)
        
        with open(export_path, 'w') as f:
            json.dump(user_data, f, default=str, indent=2)
        
        print(f"✅ Data exported to: {export_path}")
        return export_path
    
    async def delete_user_data(self, user_id: int):
        """Delete all data for a specific user (GDPR compliance)"""
        print(f"🗑️ Deleting data for user {user_id}...")
        
        collections_to_clean = [
            "users", "feedback", "transactions", 
            "cookie_logs", "warnings", "blacklist_appeals"
        ]
        
        total_deleted = 0
        
        for collection in collections_to_clean:
            result = await self.db[collection].delete_many({"user_id": user_id})
            total_deleted += result.deleted_count
            if result.deleted_count > 0:
                print(f"  Deleted {result.deleted_count} documents from {collection}")
        
        await self.db.analytics.update_many(
            {},
            {"$pull": {"commands.$[].unique_users": user_id}}
        )
        
        print(f"✅ Deleted {total_deleted} documents for user {user_id}")
        return total_deleted
    
    async def maintenance_mode(self, enable: bool, message: str = None):
        """Enable or disable maintenance mode"""
        status = "enabled" if enable else "disabled"
        print(f"🔧 Maintenance mode {status}...")
        
        update_data = {
            "maintenance_mode": enable,
            "maintenance_message": message or "Bot is under maintenance. Please try again later.",
            "maintenance_started": datetime.now(timezone.utc) if enable else None
        }
        
        await self.db.config.update_one(
            {"_id": "bot_config"},
            {"$set": update_data}
        )
        
        print(f"✅ Maintenance mode {status}")
    
    async def refresh_statistics(self):
        """Recalculate all statistics from scratch"""
        print("🔄 Refreshing all statistics...")
        
        total_users = await self.db.users.count_documents({})
        active_users = await self.db.users.count_documents({
            "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=30)}
        })
        
        total_claims = 0
        cookie_stats = {}
        
        async for user in self.db.users.find():
            total_claims += user.get("total_claims", 0)
            for cookie, count in user.get("cookie_claims", {}).items():
                cookie_stats[cookie] = cookie_stats.get(cookie, 0) + count
        
        await self.db.statistics.update_one(
            {"_id": "global_stats"},
            {
                "$set": {
                    "total_claims": cookie_stats,
                    "all_time_claims": total_claims,
                    "total_users": total_users,
                    "active_users": active_users,
                    "last_refresh": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        print("✅ Statistics refreshed successfully")
    
    async def run_all_maintenance(self):
        """Run all maintenance tasks"""
        print("🛠️ Running complete maintenance...")
        print("=" * 50)
        
        await self.backup_database()
        print()
        
        await self.fix_corrupted_data()
        print()
        
        await self.migrate_data()
        print()
        
        await self.clean_inactive_users()
        print()
        
        await self.optimize_performance()
        print()
        
        await self.refresh_statistics()
        print()
        
        await self.check_directory_stock()
        print()
        
        await self.generate_analytics_report()
        
        print("\n✅ All maintenance tasks completed!")
        print("=" * 50)
    
    async def interactive_menu(self):
        """Interactive maintenance menu"""
        while True:
            print("\n" + "=" * 50)
            print("🛠️  BOT MAINTENANCE TOOLS")
            print("=" * 50)
            print("1. Backup Database")
            print("2. Restore Database")
            print("3. Clean Inactive Users")
            print("4. Reset Weekly Stats")
            print("5. Migrate Data")
            print("6. Fix Corrupted Data")
            print("7. Optimize Performance")
            print("8. Generate Analytics Report")
            print("9. Check Cookie Stock")
            print("10. Export User Data")
            print("11. Delete User Data")
            print("12. Toggle Maintenance Mode")
            print("13. Refresh Statistics")
            print("14. Run All Maintenance")
            print("0. Exit")
            print("=" * 50)
            
            choice = input("\nSelect an option: ")
            
            try:
                if choice == "0":
                    break
                elif choice == "1":
                    await self.backup_database()
                elif choice == "2":
                    backup_dir = input("Enter backup directory path: ")
                    await self.restore_database(backup_dir)
                elif choice == "3":
                    days = int(input("Inactive for how many days? (default 90): ") or "90")
                    await self.clean_inactive_users(days)
                elif choice == "4":
                    await self.reset_weekly_stats()
                elif choice == "5":
                    await self.migrate_data()
                elif choice == "6":
                    await self.fix_corrupted_data()
                elif choice == "7":
                    await self.optimize_performance()
                elif choice == "8":
                    await self.generate_analytics_report()
                elif choice == "9":
                    await self.check_directory_stock()
                elif choice == "10":
                    user_id = int(input("Enter user ID: "))
                    await self.export_user_data(user_id)
                elif choice == "11":
                    user_id = int(input("Enter user ID: "))
                    confirm = input("Are you sure? This cannot be undone! (yes/no): ")
                    if confirm.lower() == "yes":
                        await self.delete_user_data(user_id)
                elif choice == "12":
                    enable = input("Enable maintenance mode? (yes/no): ").lower() == "yes"
                    message = input("Custom message (optional): ") or None
                    await self.maintenance_mode(enable, message)
                elif choice == "13":
                    await self.refresh_statistics()
                elif choice == "14":
                    confirm = input("Run all maintenance tasks? (yes/no): ")
                    if confirm.lower() == "yes":
                        await self.run_all_maintenance()
                else:
                    print("❌ Invalid option!")
                    
                input("\nPress Enter to continue...")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                input("\nPress Enter to continue...")
    
    async def close(self):
        """Close database connection"""
        self.client.close()

async def main():
    tools = BotMaintenanceTools()
    
    try:
        await tools.interactive_menu()
    finally:
        await tools.close()
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    asyncio.run(main())