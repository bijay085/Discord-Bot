import motor.motor_asyncio
import os
from dotenv import load_dotenv
import asyncio

load_dotenv('setup/.env')

async def fix_lottery_collection():
    MONGODB_URI = os.getenv("MONGODB_URI")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
    
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    # Check if lottery collection exists
    collections = await db.list_collection_names()
    
    if "lottery" not in collections:
        await db.create_collection("lottery")
        print("✅ Created lottery collection")
    else:
        print("✅ Lottery collection already exists")
    
    # Create index on active field
    await db.lottery.create_index("active")
    print("✅ Created index on lottery.active")
    
    # Check for any active lotteries and clean them up
    active_lotteries = await db.lottery.count_documents({"active": True})
    if active_lotteries > 1:
        # Keep only the most recent active lottery
        lotteries = await db.lottery.find({"active": True}).sort("start_time", -1).to_list(None)
        
        # Keep the first (most recent) and deactivate others
        for lottery in lotteries[1:]:
            await db.lottery.update_one(
                {"_id": lottery["_id"]},
                {"$set": {"active": False}}
            )
        print(f"✅ Cleaned up {active_lotteries - 1} duplicate active lotteries")
    
    print("✅ Lottery collection is ready!")
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_lottery_collection())