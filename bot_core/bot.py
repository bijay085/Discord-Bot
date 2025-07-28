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
        self.status_cooldowns = {}  # Track refresh cooldowns
        self.spam_violations = {}  # Track spam attempts
        
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
        
        try:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=45000,
                waitQueueTimeoutMS=10000,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                retryWrites=True,
                w='majority'
            )
            
            self.db = self.mongo_client[DATABASE_NAME]
            
            result = await self.mongo_client.admin.command('ping')
            print("✅ MongoDB connected!")
            
            await self.db_handler.initialize_database()
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
        
        print("📚 Loading cogs...")
        await self.load_cogs()
        
        self.update_presence.start()
        self.cleanup_cache.start()
        self.monitor_performance.start()
        self.cleanup_active_claims.start()
        
        print("✅ Ready!")
        
    async def load_cogs(self):
        core_cogs = [
            "cogs.cookie",
            "cogs.points",
            "cogs.admin",
            "cogs.invite",
            "cogs.directory",
            "cogs.analytics",
            "cogs.feedback"
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
            if not self.is_ready():
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
        except Exception as e:
            logger.error(f"Error updating presence: {e}")
    
    @tasks.loop(hours=1)
    async def cleanup_cache(self):
        try:
            cookie_cog = self.get_cog("CookieCog")
            if cookie_cog and hasattr(cookie_cog, 'cooldown_cache'):
                cookie_cog.cooldown_cache.clear()
                
            self.command_stats.clear()
            
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            await self.db.analytics.delete_many({"timestamp": {"$lt": cutoff}})
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
    
    @tasks.loop(minutes=10)
    async def cleanup_active_claims(self):
        try:
            if not self.is_ready():
                return
                
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
                
            latency = round(self.latency * 1000) if self.latency and not math.isnan(self.latency) else 0
            
            if latency > 200:
                print(f"⚠️ High latency: {latency}ms")
                
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            await self.db.analytics.insert_one({
                "type": "performance",
                "timestamp": datetime.now(timezone.utc),
                "latency": latency,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "guilds": len(self.guilds),
                "users": sum(g.member_count for g in self.guilds)
            })
            
        except Exception as e:
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
            # Create the status view with refresh button
            view = StatusRefreshView(self, message.author.id)
            
            # Get initial embed
            embed = await self.create_status_embed()
            
            # Send the message
            sent_message = await message.reply(embed=embed, view=view, mention_author=False)
            view.message = sent_message
            return
        
        # Process commands normally
        await self.process_commands(message)
    
    async def create_status_embed(self):
        """Create the status embed with current statistics"""
        # Get bot statistics
        total_cookies = await self.get_total_cookies()
        total_users = await self.db.users.count_documents({})
        active_users = await self.db.users.count_documents({
            "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=1)}
        })
        
        # Create stats embed
        embed = discord.Embed(
            title="🍪 Cookie Bot Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="⏰ Uptime",
            value=f"```{self.get_uptime()}```",
            inline=True
        )
        
        embed.add_field(
            name="📡 Latency",
            value=f"```{round(self.latency * 1000)}ms```",
            inline=True
        )
        
        embed.add_field(
            name="📊 Servers",
            value=f"```{len(self.guilds):,}```",
            inline=True
        )
        
        embed.add_field(
            name="👥 Total Users",
            value=f"```{sum(g.member_count for g in self.guilds):,}```",
            inline=True
        )
        
        embed.add_field(
            name="📝 Registered",
            value=f"```{total_users:,}```",
            inline=True
        )
        
        embed.add_field(
            name="🟢 Active (24h)",
            value=f"```{active_users:,}```",
            inline=True
        )
        
        embed.add_field(
            name="🍪 Total Cookies Claimed",
            value=f"```{total_cookies:,}```",
            inline=False
        )
        
        embed.add_field(
            name="💾 Memory Usage",
            value=f"```{psutil.virtual_memory().percent}%```",
            inline=True
        )
        
        embed.add_field(
            name="⚡ Commands",
            value=f"```{len(self.commands)}```",
            inline=True
        )
        
        embed.set_author(name=self.user.name, icon_url=self.user.avatar.url)
        embed.set_footer(text="Use /help to see all commands")
        
        return embed
    
    async def get_total_cookies(self):
        """Get total cookies distributed"""
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        return stats.get("all_time_claims", 0) if stats else 0
    
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
        
        config = await self.db.config.find_one({"_id": "bot_config"})
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

class StatusRefreshView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=None)  # No timeout - button works forever
        self.bot = bot
        self.user_id = user_id
        self.message = None
        
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check cooldown
        user_id = interaction.user.id
        now = datetime.now(timezone.utc)
        
        # Check if user has a penalty
        if user_id in self.bot.spam_violations:
            penalty_end = self.bot.spam_violations[user_id]
            if now < penalty_end:
                remaining_minutes = (penalty_end - now).total_seconds() / 60
                await interaction.response.send_message(
                    f"🚫 You have been temporarily restricted for spamming!\n"
                    f"⏰ Try again in **{remaining_minutes:.1f}** minutes.",
                    ephemeral=True
                )
                return
            else:
                # Penalty expired, remove it
                del self.bot.spam_violations[user_id]
        
        # Check regular cooldown
        if user_id in self.bot.status_cooldowns:
            last_refresh, violation_count = self.bot.status_cooldowns[user_id]
            time_passed = (now - last_refresh).total_seconds()
            
            if time_passed < 120:  # 2 minute cooldown
                remaining = 120 - time_passed
                
                # Increment violation count
                new_violation_count = violation_count + 1
                self.bot.status_cooldowns[user_id] = (last_refresh, new_violation_count)
                
                # Check if they've tried 3 times during cooldown
                if new_violation_count >= 3:
                    # Apply 20-minute penalty
                    penalty_end = now + timedelta(minutes=20)
                    self.bot.spam_violations[user_id] = penalty_end
                    
                    # Reset their cooldown tracking
                    if user_id in self.bot.status_cooldowns:
                        del self.bot.status_cooldowns[user_id]
                    
                    await interaction.response.send_message(
                        f"🚫 **SPAM DETECTED!**\n"
                        f"You have been restricted for **20 minutes** for attempting to spam the refresh button.\n"
                        f"Please be patient and wait for cooldowns!",
                        ephemeral=True
                    )
                    return
                else:
                    # Show remaining cooldown
                    minutes = int(remaining // 60)
                    seconds = int(remaining % 60)
                    await interaction.response.send_message(
                        f"⏰ Please wait **{minutes}m {seconds}s** before refreshing again!\n"
                        f"⚠️ Warning: {3 - new_violation_count} more attempts during cooldown will result in a 20-minute restriction.",
                        ephemeral=True
                    )
                    return
        
        # Update cooldown (last refresh time, violation count)
        self.bot.status_cooldowns[user_id] = (now, 0)
        
        # Defer the response
        await interaction.response.defer()
        
        # Get new embed
        new_embed = await self.bot.create_status_embed()
        
        # Update the message
        await interaction.followup.edit_message(
            message_id=self.message.id,
            embed=new_embed,
            view=self
        )