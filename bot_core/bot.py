# bot_core/bot.py - Key improvements for stability

import discord
from discord.ext import commands, tasks
import motor.motor_asyncio
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import warnings
import aiohttp
import platform
import psutil
import math
from .logger import setup_logging, webhook_handler
from .views import BotControlView
from .events import EventHandler
from .database import DatabaseHandler

load_dotenv('setup/.env')
warnings.filterwarnings("ignore", message="PyNaCl is not installed")

logger = setup_logging()

class CookieBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.presences = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for /help | Cookie Bot 🍪"
            ),
            status=discord.Status.online,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                roles=False,
                replied_user=False
            )
        )
        
        self.mongo_client = None
        self.db = None
        self.start_time = datetime.now(timezone.utc)
        self.session = None
        self.command_stats = {}
        self.error_webhooks = {}
        self.status_messages = {}
        self.active_claims = {}
        self.db_handler = DatabaseHandler(self)
        self.event_handler = EventHandler(self)
        self._connection_check_task = None
        
    async def setup_hook(self):
        print("🚀 Initializing...")
        
        self.session = aiohttp.ClientSession()
        webhook_handler.session = self.session
        
        MONGODB_URI = os.getenv("MONGODB_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        ERROR_WEBHOOK = os.getenv("ERROR_WEBHOOK")
        
        if ERROR_WEBHOOK:
            webhook_handler.webhook_url = ERROR_WEBHOOK
        
        if not MONGODB_URI:
            logger.error("❌ MONGODB_URI not found!")
            raise ValueError("MONGODB_URI is required")
            
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN not found!")
            raise ValueError("BOT_TOKEN is required")
        
        print(f"🔗 Connecting to MongoDB...")
        
        # Initialize MongoDB with improved settings
        try:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
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
                heartbeatFrequencyMS=10000,
                socketTimeoutMS=30000
            )
            
            self.db = self.mongo_client[DATABASE_NAME]
            
            # Test connection
            result = await self.mongo_client.admin.command('ping')
            print("✅ MongoDB connected!")
            
            await self.db_handler.initialize_database()
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
        
        print("📚 Loading cogs...")
        await self.load_cogs()
        
        # Start background tasks with error handling
        self.update_presence.start()
        self.cleanup_cache.start()
        self.monitor_performance.start()
        self.cleanup_active_claims.start()
        self._connection_check_task = asyncio.create_task(self._monitor_db_connection())
        
        print("✅ Ready!")
    
    async def _monitor_db_connection(self):
        """Monitor database connection health"""
        while not self.is_closed():
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self.db_handler.ensure_connection()
            except Exception as e:
                logger.error(f"Database connection monitor error: {e}")
        
    async def load_cogs(self):
        core_cogs = [
            "cogs.cookie",
            "cogs.points",
            "cogs.admin",
            "cogs.invite",
            "cogs.directory",
            "cogs.analytics",
            "cogs.feedback",
            "cogs.givecookie"
        ]
        
        loaded = 0
        failed = 0
        
        for cog in core_cogs:
            try:
                await self.load_extension(cog)
                loaded += 1
            except Exception as e:
                logger.error(f"Failed to load {cog}: {e}")
                failed += 1
        
        print(f"📦 Core: {loaded} loaded, {failed} failed")
        
        try:
            await self.load_extension("cogs.entertainment_handler")
        except Exception as e:
            print(f"❌ Entertainment failed: {e}")
    
    @tasks.loop(minutes=5)
    async def update_presence(self):
        try:
            if not self.is_ready() or not self.ws:
                return
                
            presences = [
                {"type": discord.ActivityType.watching, "name": f"{len(self.guilds)} servers"},
                {"type": discord.ActivityType.playing, "name": "with cookies 🍪"},
                {"type": discord.ActivityType.listening, "name": "/help"},
                {"type": discord.ActivityType.watching, "name": f"{sum(g.member_count for g in self.guilds):,} users"},
                {"type": discord.ActivityType.competing, "name": "cookie distribution"}
            ]
            
            presence = presences[int(datetime.now().minute / 5) % len(presences)]
            
            await self.change_presence(
                activity=discord.Activity(
                    type=presence["type"],
                    name=presence["name"]
                ),
                status=discord.Status.online
            )
        except discord.errors.InvalidArgument:
            pass  # Ignore if websocket is closing
        except Exception as e:
            if "Cannot write to closing transport" not in str(e):
                logger.error(f"Error updating presence: {e}")
    
    @tasks.loop(hours=1)
    async def cleanup_cache(self):
        try:
            cookie_cog = self.get_cog("CookieCog")
            if cookie_cog and hasattr(cookie_cog, 'cooldown_cache'):
                cookie_cog.cooldown_cache.clear()
                
            self.command_stats.clear()
            
            # Clean old analytics with safe operation
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            await self.db_handler.safe_db_operation(
                self.db.analytics.delete_many,
                {"timestamp": {"$lt": cutoff}}
            )
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
    
    @tasks.loop(minutes=10)
    async def cleanup_active_claims(self):
        try:
            if not self.is_ready():
                return
                
            # Clean up orphaned claims
            for user_id in list(self.active_claims.keys()):
                if not self.get_user(user_id):
                    del self.active_claims[user_id]
                    
            cookie_cog = self.get_cog("CookieCog")
            if cookie_cog and hasattr(cookie_cog, 'active_claims'):
                for user_id in list(cookie_cog.active_claims.keys()):
                    if not self.get_user(user_id):
                        del cookie_cog.active_claims[user_id]
                        
        except Exception as e:
            logger.error(f"Error cleaning up active claims: {e}")
    
    @tasks.loop(minutes=10)
    async def monitor_performance(self):
        try:
            if not self.is_ready():
                return
            
            # Safe latency calculation
            if self.latency and not math.isnan(self.latency) and not math.isinf(self.latency):
                latency = round(self.latency * 1000)
            else:
                latency = 0
                
            if latency > 200:
                print(f"⚠️ High latency: {latency}ms")
                
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Use safe db operation
            await self.db_handler.safe_db_operation(
                self.db.analytics.insert_one,
                {
                    "type": "performance",
                    "timestamp": datetime.now(timezone.utc),
                    "latency": latency,
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "guilds": len(self.guilds),
                    "users": sum(g.member_count for g in self.guilds)
                }
            )
            
        except Exception as e:
            if "cannot convert float infinity to integer" not in str(e):
                logger.error(f"Error monitoring performance: {e}")
    
    @update_presence.before_loop
    async def before_update_presence(self):
        await self.wait_until_ready()
    
    @cleanup_cache.before_loop
    async def before_cleanup_cache(self):
        await self.wait_until_ready()
    
    @monitor_performance.before_loop
    async def before_monitor_performance(self):
        await self.wait_until_ready()
        
    @cleanup_active_claims.before_loop
    async def before_cleanup_active_claims(self):
        await self.wait_until_ready()
    
    async def on_ready(self):
        await self.event_handler.on_ready()
    
    async def on_message(self, message):
        # Ignore messages from bots
        if message.author.bot:
            return
        
        # Check if message is ONLY a mention of the bot
        if message.content.strip() == f"<@{self.user.id}>" or message.content.strip() == f"<@!{self.user.id}>":
            # Create simple status embed for mentions
            embed = discord.Embed(
                title="👋 Hey there! I'm Cookie Bot!",
                description="Your premium cookie distribution system",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Basic info with safe latency
            latency = round(self.latency * 1000) if self.latency and not math.isnan(self.latency) else 0
            embed.add_field(
                name="🤖 Bot Info",
                value=f"**Uptime:** {self.get_uptime()}\n"
                      f"**Ping:** {latency}ms\n"
                      f"**Servers:** {len(self.guilds)}",
                inline=True
            )
            
            # Quick stats with safe db operation
            try:
                total_cookies = await self.get_total_cookies()
            except:
                total_cookies = 0
                
            embed.add_field(
                name="📊 Quick Stats",
                value=f"**Cookies Served:** {total_cookies:,}\n"
                      f"**Total Users:** {sum(g.member_count for g in self.guilds):,}\n"
                      f"**Commands:** {len(self.commands)}",
                inline=True
            )
            
            # Help info
            embed.add_field(
                name="🔧 Getting Started",
                value="• `/help` - View all commands\n"
                      "• `/cookie` - Claim a cookie\n"
                      "• `/daily` - Get daily points\n"
                      "• `/points` - Check balance",
                inline=False
            )
            
            embed.set_thumbnail(url=self.user.avatar.url)
            embed.set_footer(text="Use /help for detailed commands • Cookie Bot v2.0")
            
            await message.reply(embed=embed, mention_author=False)
            return
        
        # Process commands normally
        await self.process_commands(message)
    
    async def get_total_cookies(self):
        """Get total cookies distributed with safe operation"""
        try:
            stats = await self.db_handler.safe_db_operation(
                self.db.statistics.find_one, {"_id": "global_stats"}
            )
            return stats.get("all_time_claims", 0) if stats else 0
        except:
            return 0
    
    async def on_guild_join(self, guild):
        await self.event_handler.on_guild_join(guild)
    
    async def on_guild_remove(self, guild):
        await self.event_handler.on_guild_remove(guild)
    
    async def on_application_command(self, interaction: discord.Interaction):
        await self.event_handler.on_application_command(interaction)
    
    async def on_command_error(self, ctx, error):
        await self.event_handler.on_command_error(ctx, error)
    
    async def close(self):
        print("🛑 Shutting down...")
        
        # Cancel background tasks
        if self._connection_check_task:
            self._connection_check_task.cancel()
        
        # Send shutdown message with safe db operation
        try:
            config = await self.db_handler.safe_db_operation(
                self.db.config.find_one, {"_id": "bot_config"}
            )
            if config and config.get("main_log_channel"):
                channel = self.get_channel(config["main_log_channel"])
                if channel:
                    embed = discord.Embed(
                        title="🔴 Bot Offline",
                        description="Cookie Bot is shutting down...",
                        color=0xE74C3C,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
                    embed.add_field(name="Commands Processed", value=f"{sum(self.command_stats.values()):,}", inline=True)
                    await channel.send(embed=embed)
        except:
            pass
        
        if self.session and not self.session.closed:
            await self.session.close()
            
        if self.mongo_client:
            self.mongo_client.close()
            
        await super().close()
        print("✅ Shutdown complete")
    
    def get_uptime(self):
        delta = datetime.now(timezone.utc) - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
            
        return " ".join(parts)