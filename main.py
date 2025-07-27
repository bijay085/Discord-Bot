import discord
from discord.ext import commands, tasks
import motor.motor_asyncio
import os
import asyncio
from dotenv import load_dotenv
import logging
from datetime import datetime, timezone, timedelta
import sys
import warnings
import aiohttp
import platform
import psutil
import json
import math
from typing import Optional, Dict, List

load_dotenv('setup/.env')

warnings.filterwarnings("ignore", message="PyNaCl is not installed")

class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logging.getLogger('discord.client').setLevel(logging.ERROR)
logger = logging.getLogger('CookieBot')

class BotControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
    @discord.ui.button(label="System Status", style=discord.ButtonStyle.primary, emoji="📊")
    async def system_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        embed = discord.Embed(
            title="🖥️ System Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="CPU Usage", value=f"{cpu_percent}%", inline=True)
        embed.add_field(name="RAM Usage", value=f"{memory.percent}%", inline=True)
        embed.add_field(name="Disk Usage", value=f"{disk.percent}%", inline=True)
        embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="Discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Platform", value=platform.system(), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Bot Stats", style=discord.ButtonStyle.success, emoji="📈")
    async def bot_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_users = sum(g.member_count for g in self.bot.guilds)
        total_claims = await self.bot.db.statistics.find_one({"_id": "global_stats"})
        
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(name="Users", value=f"{total_users:,}", inline=True)
        embed.add_field(name="Channels", value=f"{sum(len(g.channels) for g in self.bot.guilds):,}", inline=True)
        
        if total_claims:
            embed.add_field(
                name="Total Claims", 
                value=f"{total_claims.get('all_time_claims', 0):,}", 
                inline=True
            )
        
        embed.add_field(name="Uptime", value=self.bot.get_uptime(), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.edit_original_response(embed=self.create_status_embed())
    
    def get_uptime(self):
        delta = datetime.now(timezone.utc) - self.bot.start_time
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
    
    def create_status_embed(self):
        status_emoji = "🟢" if self.bot.ws else "🔴"
        embed = discord.Embed(
            title=f"{status_emoji} Cookie Bot Status",
            description="Bot is fully operational and ready to serve cookies!",
            color=discord.Color.green() if self.bot.ws else discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Status", value="Online" if self.bot.ws else "Offline", inline=True)
        embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
        embed.add_field(name="Version", value="v2.0.0", inline=True)
        embed.set_footer(text="Cookie Bot Premium", icon_url=self.bot.user.avatar.url if self.bot.user else None)
        return embed

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
        
    async def setup_hook(self):
        logger.info("🚀 Initializing Cookie Bot...")
        
        self.session = aiohttp.ClientSession()
        
        MONGODB_URI = os.getenv("MONGODB_URI")
        DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        
        if not MONGODB_URI:
            logger.error("❌ MONGODB_URI not found in environment variables!")
            raise ValueError("MONGODB_URI is required")
            
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN not found in environment variables!")
            raise ValueError("BOT_TOKEN is required")
        
        logger.info(f"🔗 Connecting to MongoDB...")
        logger.info(f"📦 Database: {DATABASE_NAME}")
        
        try:
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=45000,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                retryWrites=True,
                w='majority'
            )
            
            self.db = self.mongo_client[DATABASE_NAME]
            
            logger.info("🔍 Testing MongoDB connection...")
            result = await self.mongo_client.admin.command('ping')
            logger.info("✅ Successfully connected to MongoDB!")
            
            await self.initialize_database()
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            logger.error(f"📌 Make sure your MongoDB URI is correct and your IP is whitelisted")
            raise
        
        logger.info("📚 Loading cogs...")
        await self.load_cogs()
        
        self.update_presence.start()
        self.cleanup_cache.start()
        self.monitor_performance.start()
        
        logger.info("✅ Setup complete!")
        
    async def initialize_database(self):
        collections = ['users', 'servers', 'config', 'statistics', 'feedback', 'analytics']
        existing = await self.db.list_collection_names()
        
        for collection in collections:
            if collection not in existing:
                await self.db.create_collection(collection)
                logger.info(f"📂 Created collection: {collection}")
        
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
                existing_indexes = await self.db[collection].list_indexes().to_list(None)
                existing_names = {idx['name'] for idx in existing_indexes}
                
                for index_config in index_list:
                    index_name = '_'.join([f"{k}_{v}" for k, v in index_config['keys']])
                    
                    if index_name not in existing_names:
                        await self.db[collection].create_index(
                            index_config['keys'],
                            unique=index_config.get('unique', False)
                        )
                        logger.info(f"📑 Created index {index_name} on {collection}")
                    else:
                        logger.info(f"✓ Index {index_name} already exists on {collection}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not create indexes for {collection}: {e}")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if not config:
            await self.db.config.insert_one({
                "_id": "bot_config",
                "maintenance_mode": False,
                "feedback_minutes": 15,
                "version": "2.0.0",
                "created_at": datetime.now(timezone.utc)
            })
        
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        if not stats:
            await self.db.statistics.insert_one({
                "_id": "global_stats",
                "total_claims": {},
                "weekly_claims": {},
                "all_time_claims": 0,
                "created_at": datetime.now(timezone.utc)
            })
        
    async def load_cogs(self):
        cogs = [
            "cogs.cookie",
            "cogs.points",
            "cogs.admin",
            "cogs.invite",
            "cogs.directory",
            "cogs.analytics",
            "cogs.help"
        ]
        
        loaded = 0
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"✅ Loaded cog: {cog}")
                loaded += 1
            except Exception as e:
                logger.error(f"❌ Failed to load cog {cog}: {e}")
        
        logger.info(f"📦 Loaded {loaded}/{len(cogs)} cogs successfully")
    
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
    async def monitor_performance(self):
        try:
            if not self.is_ready():
                return
                
            latency = round(self.latency * 1000) if self.latency and not math.isnan(self.latency) else 0
            
            if latency > 200:
                logger.warning(f"⚠️ High latency detected: {latency}ms")
                
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
    
    async def on_ready(self):
        logger.info(f"✅ Bot logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"🌐 Connected to {len(self.guilds)} servers with {sum(g.member_count for g in self.guilds):,} total users")
        
        try:
            # Sync commands globally
            synced = await self.tree.sync()
            logger.info(f"🔄 Synced {len(synced)} slash commands globally")
            
            # Get command count for logging
            all_commands = list(self.tree.get_commands())
            guild_commands = list(self.tree.get_commands(guild=None))
            
            logger.info(f"📋 Total commands available: {len(all_commands)}")
            
            # Log guild info without additional syncing
            for guild in self.guilds[:5]:
                logger.info(f"  ✓ Connected to {guild.name} ({guild.member_count} members)")
                    
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.get_channel(config["main_log_channel"])
            if channel:
                embed = discord.Embed(
                    title="🟢 Bot Online",
                    description=f"Cookie Bot is now operational and ready to serve!",
                    color=0x2ECC71,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="🖥️ Servers", value=f"**{len(self.guilds)}**", inline=True)
                embed.add_field(name="👥 Users", value=f"**{sum(g.member_count for g in self.guilds):,}**", inline=True)
                embed.add_field(name="📡 Latency", value=f"**{round(self.latency * 1000)}ms**", inline=True)
                embed.add_field(name="🐍 Python", value=f"**{platform.python_version()}**", inline=True)
                embed.add_field(name="📚 Discord.py", value=f"**{discord.__version__}**", inline=True)
                embed.add_field(name="💾 RAM", value=f"**{psutil.virtual_memory().percent}%**", inline=True)
                embed.set_thumbnail(url=self.user.avatar.url)
                embed.set_footer(text="Cookie Bot Premium v2.0", icon_url=self.user.avatar.url)
                
                view = BotControlView(self)
                message = await channel.send(embed=view.create_status_embed(), view=view)
                self.status_messages[channel.id] = message.id
    
    async def on_guild_join(self, guild):
        logger.info(f"🎉 Joined new server: {guild.name} (ID: {guild.id}) with {guild.member_count} members")
        
        embed = discord.Embed(
            title="🍪 Welcome to Cookie Bot Premium!",
            description=(
                "Thank you for choosing Cookie Bot - the premium cookie distribution system!\n\n"
                "**🚀 Quick Start Guide:**"
            ),
            color=0x7289DA,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="1️⃣ Initial Setup",
            value="An administrator must run `/setup` to configure channels and settings",
            inline=False
        )
        embed.add_field(
            name="2️⃣ Configure Roles",
            value="Use `/rolesetup` to set up role-based benefits and access",
            inline=False
        )
        embed.add_field(
            name="3️⃣ Add Cookies",
            value="Upload cookie files to directories specified in setup",
            inline=False
        )
        
        embed.add_field(
            name="✨ Key Features",
            value=(
                "• **Premium Cookies** - High-quality account distribution\n"
                "• **Points Economy** - Earn and spend points for cookies\n"
                "• **Smart Cooldowns** - Role-based cooldown reduction\n"
                "• **Trust System** - Build trust through feedback\n"
                "• **Analytics** - Track usage and performance\n"
                "• **Auto-Moderation** - Automatic blacklist for rule breakers"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📚 Commands",
            value=(
                "• `/help` - View all commands\n"
                "• `/cookie` - Claim a cookie\n"
                "• `/daily` - Get daily points\n"
                "• `/points` - Check your balance\n"
                "• `/leaderboard` - View top users"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔗 Important Links",
            value=(
                "[Support Server](https://discord.gg/your-server)\n"
                "[Documentation](https://your-docs.com)\n"
                "[Premium Features](https://your-site.com)"
            ),
            inline=False
        )
        
        embed.set_thumbnail(url=self.user.avatar.url)
        embed.set_footer(text="Cookie Bot Premium v2.0 - Your trusted cookie provider")
        
        welcome_sent = False
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and channel.permissions_for(guild.me).embed_links:
                try:
                    button1 = discord.ui.Button(label="Quick Setup", emoji="⚙️", style=discord.ButtonStyle.primary)
                    button2 = discord.ui.Button(label="Documentation", emoji="📚", style=discord.ButtonStyle.link, url="https://your-docs.com")
                    
                    async def setup_callback(interaction: discord.Interaction):
                        if not interaction.user.guild_permissions.administrator:
                            await interaction.response.send_message("❌ Only administrators can run setup!", ephemeral=True)
                            return
                        await interaction.response.send_message("Please run `/setup` to begin configuration!", ephemeral=True)
                    
                    button1.callback = setup_callback
                    
                    view = discord.ui.View()
                    view.add_item(button1)
                    view.add_item(button2)
                    
                    await channel.send(embed=embed, view=view)
                    welcome_sent = True
                    break
                except:
                    continue
        
        if not welcome_sent:
            logger.warning(f"Could not send welcome message to {guild.name}")
        
        await self.db.servers.insert_one({
            "server_id": guild.id,
            "server_name": guild.name,
            "joined_at": datetime.now(timezone.utc),
            "member_count": guild.member_count,
            "owner_id": guild.owner_id,
            "enabled": False,
            "setup_complete": False
        })
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.get_channel(config["main_log_channel"])
            if channel:
                log_embed = discord.Embed(
                    title="📥 New Server Joined",
                    color=0x2ECC71,
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="🏷️ Server", value=guild.name, inline=True)
                log_embed.add_field(name="🆔 ID", value=f"`{guild.id}`", inline=True)
                log_embed.add_field(name="👥 Members", value=f"**{guild.member_count:,}**", inline=True)
                log_embed.add_field(name="👑 Owner", value=f"{guild.owner.mention if guild.owner else 'Unknown'}", inline=True)
                log_embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
                log_embed.add_field(name="📊 Total Servers", value=f"**{len(self.guilds)}**", inline=True)
                
                if guild.icon:
                    log_embed.set_thumbnail(url=guild.icon.url)
                
                if guild.banner:
                    log_embed.set_image(url=guild.banner.url)
                    
                await channel.send(embed=log_embed)
    
    async def on_guild_remove(self, guild):
        logger.info(f"👋 Removed from server: {guild.name} (ID: {guild.id})")
        
        await self.db.servers.update_one(
            {"server_id": guild.id},
            {
                "$set": {
                    "left_at": datetime.now(timezone.utc),
                    "active": False
                }
            }
        )
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.get_channel(config["main_log_channel"])
            if channel:
                log_embed = discord.Embed(
                    title="📤 Server Left",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="🏷️ Server", value=guild.name, inline=True)
                log_embed.add_field(name="🆔 ID", value=f"`{guild.id}`", inline=True)
                log_embed.add_field(name="👥 Members", value=f"**{guild.member_count:,}**", inline=True)
                log_embed.add_field(name="📊 Total Servers", value=f"**{len(self.guilds)}**", inline=True)
                log_embed.add_field(name="💔 Total Users Lost", value=f"**{guild.member_count:,}**", inline=True)
                
                server_data = await self.db.servers.find_one({"server_id": guild.id})
                if server_data and server_data.get("joined_at"):
                    duration = datetime.now(timezone.utc) - server_data["joined_at"]
                    log_embed.add_field(
                        name="⏱️ Duration", 
                        value=f"{duration.days} days",
                        inline=True
                    )
                
                if guild.icon:
                    log_embed.set_thumbnail(url=guild.icon.url)
                    
                await channel.send(embed=log_embed)
    
    async def on_application_command(self, interaction: discord.Interaction):
        command_name = interaction.data.get("name", "unknown")
        
        self.command_stats[command_name] = self.command_stats.get(command_name, 0) + 1
        
        await self.db.analytics.insert_one({
            "type": "command_usage",
            "command": command_name,
            "user_id": interaction.user.id,
            "guild_id": interaction.guild_id if interaction.guild else None,
            "timestamp": datetime.now(timezone.utc)
        })
    
    async def on_command_error(self, ctx, error):
        error_embed = discord.Embed(
            title="❌ Command Error",
            color=0xFF6B6B,
            timestamp=datetime.now(timezone.utc)
        )
        
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            error_embed.description = f"Missing required argument: `{error.param.name}`"
            error_embed.add_field(
                name="Usage",
                value=f"`{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
                inline=False
            )
        elif isinstance(error, commands.BadArgument):
            error_embed.description = "Invalid argument provided"
            error_embed.add_field(
                name="Tip",
                value="Check the command help for proper usage",
                inline=False
            )
        elif isinstance(error, commands.CheckFailure):
            error_embed.description = "You don't have permission to use this command"
            error_embed.add_field(
                name="Required",
                value="Administrator permissions or specific roles",
                inline=False
            )
        elif isinstance(error, commands.CommandOnCooldown):
            error_embed.description = f"Command on cooldown! Try again in {error.retry_after:.1f}s"
        else:
            logger.error(f"Unhandled error in {ctx.command}: {error}", exc_info=error)
            error_embed.description = "An unexpected error occurred"
            error_embed.add_field(
                name="Error Details",
                value=f"```{str(error)[:100]}```",
                inline=False
            )
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            if config and config.get("error_webhook"):
                webhook = self.error_webhooks.get("global")
                if not webhook:
                    webhook = discord.Webhook.from_url(
                        config["error_webhook"],
                        session=self.session
                    )
                    self.error_webhooks["global"] = webhook
                
                error_details = discord.Embed(
                    title=f"Error in {ctx.command.name}",
                    description=f"```{str(error)}```",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                error_details.add_field(name="User", value=f"{ctx.author} ({ctx.author.id})")
                error_details.add_field(name="Guild", value=f"{ctx.guild.name if ctx.guild else 'DM'}")
                error_details.add_field(name="Channel", value=f"{ctx.channel.name if hasattr(ctx.channel, 'name') else 'DM'}")
                
                await webhook.send(embed=error_details)
        
        await ctx.send(embed=error_embed, ephemeral=True)
    
    async def close(self):
        logger.info("🛑 Shutting down Cookie Bot...")
        
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
                embed.add_field(name="Uptime", value=self.bot.get_uptime(), inline=True)
                embed.add_field(name="Commands Processed", value=f"{sum(self.command_stats.values()):,}", inline=True)
                await channel.send(embed=embed)
        
        if self.session and not self.session.closed:
            await self.session.close()
            
        if self.mongo_client:
            self.mongo_client.close()
            
        await super().close()
        logger.info("✅ Shutdown complete")
    
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

async def main():
    print("""
    ╔═══════════════════════════════════════╗
    ║      🍪 COOKIE BOT PREMIUM v2.0 🍪     ║
    ╠═══════════════════════════════════════╣
    ║  Advanced Cookie Distribution System   ║
    ║      Created with ❤️ by YourName       ║
    ╚═══════════════════════════════════════╝
    """)
    
    bot = CookieBot()
    
    try:
        logger.info("🚀 Starting Cookie Bot...")
        await bot.start(os.getenv("BOT_TOKEN"))
    except KeyboardInterrupt:
        logger.info("⌨️ Received interrupt signal")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")