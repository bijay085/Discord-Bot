# main.py

import discord
from discord.ext import commands
import motor.motor_asyncio
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
BOT_TOKEN = os.getenv("BOT_TOKEN")

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = mongo_client[DATABASE_NAME]

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    print(f"Connected to {len(bot.guilds)} servers")
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}", ephemeral=True)
    else:
        print(f"Error: {error}")

async def load_cogs():
    cogs = [
        "cogs.cookie",
        "cogs.points",
        "cogs.admin",
        "cogs.invite",
        "cogs.directory"
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        except Exception as e:
            print(f"Failed to load cog {cog}: {e}")

async def main():
    await load_cogs()
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    bot.db = db
    asyncio.run(main())