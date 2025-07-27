import discord
from discord.ext import commands
import motor.motor_asyncio
import os
import asyncio
from dotenv import load_dotenv
import logging
from datetime import datetime, timezone
import sys
import warnings

load_dotenv('setup/.env')

# Suppress PyNaCl warning since we don't use voice
warnings.filterwarnings("ignore", message="PyNaCl is not installed")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    encoding='utf-8'
)

# Filter out the PyNaCl warning from discord.py
logging.getLogger('discord.client').setLevel(logging.ERROR)

logger = logging.getLogger('CookieBot')

class CookieBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for /help | Cookie Bot 🍪"
            ),
            status=discord.Status.online
        )
        
        self.mongo_client = None
        self.db = None
        self.start_time = datetime.now(timezone.utc)
        
    async def setup_hook(self):
        logger.info("Setting up bot...")
        
        MONGODB_URI = os.getenv("MONGODB_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        
        if not MONGODB_URI:
            logger.error("MONGODB_URI not found in environment variables!")
            raise ValueError("MONGODB_URI is required")
            
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not found in environment variables!")
            raise ValueError("BOT_TOKEN is required")
        
        logger.info(f"Connecting to MongoDB...")
        logger.info(f"Database: {DATABASE_NAME}")
        
        try:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=45000,
                serverSelectionTimeoutMS=5000
            )
            
            self.db = self.mongo_client[DATABASE_NAME]
            
            logger.info("MongoDB client created, testing connection...")
            await self.mongo_client.admin.command('ping')
            logger.info("Successfully connected to MongoDB!")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            logger.error(f"Make sure your MongoDB URI is correct and your IP is whitelisted")
            raise
        
        logger.info("Loading cogs...")
        await self.load_cogs()
        logger.info("Setup complete!")
        
    async def load_cogs(self):
        cogs = [
            "cogs.cookie",
            "cogs.points",
            "cogs.admin",
            "cogs.invite",
            "cogs.directory"
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")
    
    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} servers")
        
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.get_channel(config["main_log_channel"])
            if channel:
                embed = discord.Embed(
                    title="🟢 Bot Online",
                    description=f"Cookie Bot is now operational!",
                    color=0x2ECC71,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Servers", value=f"**{len(self.guilds)}**", inline=True)
                embed.add_field(name="Users", value=f"**{sum(g.member_count for g in self.guilds):,}**", inline=True)
                embed.add_field(name="Latency", value=f"**{round(self.latency * 1000)}ms**", inline=True)
                embed.set_footer(text="Cookie Bot", icon_url=self.user.avatar.url)
                await channel.send(embed=embed)
    
    async def on_guild_join(self, guild):
        logger.info(f"Joined new server: {guild.name} (ID: {guild.id})")
        
        embed = discord.Embed(
            title="🍪 Welcome to Cookie Bot!",
            description=(
                "Thank you for adding me to your server!\n\n"
                "**Quick Setup:**\n"
                "An administrator needs to run `/setup` to configure the bot.\n\n"
                "**Key Features:**\n"
                "• Premium cookie distribution system\n"
                "• Points-based economy\n"
                "• Role-based benefits\n"
                "• Automated feedback tracking\n\n"
                "Use `/help` for a complete command list!"
            ),
            color=0x7289DA
        )
        embed.set_thumbnail(url=self.user.avatar.url)
        embed.set_footer(text="Cookie Bot - Your premium cookie provider")
        
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(embed=embed)
                    break
                except:
                    continue
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.get_channel(config["main_log_channel"])
            if channel:
                log_embed = discord.Embed(
                    title="📥 New Server Joined",
                    color=0x2ECC71,
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="Server", value=guild.name, inline=True)
                log_embed.add_field(name="ID", value=guild.id, inline=True)
                log_embed.add_field(name="Members", value=f"**{guild.member_count:,}**", inline=True)
                log_embed.add_field(name="Owner", value=f"{guild.owner.mention if guild.owner else 'Unknown'}", inline=True)
                log_embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
                log_embed.add_field(name="Total Servers", value=f"**{len(self.guilds)}**", inline=True)
                
                if guild.icon:
                    log_embed.set_thumbnail(url=guild.icon.url)
                    
                await channel.send(embed=log_embed)
    
    async def on_guild_remove(self, guild):
        logger.info(f"Removed from server: {guild.name} (ID: {guild.id})")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.get_channel(config["main_log_channel"])
            if channel:
                log_embed = discord.Embed(
                    title="📤 Server Left",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="Server", value=guild.name, inline=True)
                log_embed.add_field(name="ID", value=guild.id, inline=True)
                log_embed.add_field(name="Members", value=f"**{guild.member_count:,}**", inline=True)
                log_embed.add_field(name="Total Servers", value=f"**{len(self.guilds)}**", inline=True)
                
                if guild.icon:
                    log_embed.set_thumbnail(url=guild.icon.url)
                    
                await channel.send(embed=log_embed)
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Missing Argument",
                description=f"You're missing a required argument: `{error.param.name}`",
                color=0xFF6B6B
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ Invalid Argument",
                description="One of your arguments is invalid. Please check and try again.",
                color=0xFF6B6B
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.CheckFailure):
            embed = discord.Embed(
                title="🔒 Access Denied",
                description="You don't have permission to use this command!",
                color=0xFF6B6B
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            logger.error(f"Unhandled error: {error}")
            embed = discord.Embed(
                title="❌ An Error Occurred",
                description="Something went wrong while processing your command.",
                color=0xFF6B6B
            )
            await ctx.send(embed=embed, ephemeral=True)
    
    async def close(self):
        logger.info("Shutting down bot...")
        if self.mongo_client:
            self.mongo_client.close()
        await super().close()

async def main():
    bot = CookieBot()
    
    try:
        await bot.start(os.getenv("BOT_TOKEN"))
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())