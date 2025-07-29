import discord
from discord.ext import commands
from discord import app_commands
import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List

load_dotenv('setup/.env')

class SetupWizardBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.db = None
        self.config = None

bot = SetupWizardBot()

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "1192694890530869369"))

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
bot.db = mongo_client[DATABASE_NAME]

class SetupWizardView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.current_step = 0
        self.setup_data = {
            "channels": {},
            "roles": {},
            "cookies": {},
            "settings": {},
            "games": {}
        }
        
    @discord.ui.button(label="Start Setup", style=discord.ButtonStyle.primary, emoji="🚀")
    async def start_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the setup initiator can use this!", ephemeral=True)
            return
            
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.run_setup_wizard()
        
    async def run_setup_wizard(self):
        steps = [
            self.setup_channels,
            self.setup_roles,
            self.configure_cookies,
            self.configure_games,
            self.configure_settings,
            self.finalize_setup
        ]
        
        for step in steps:
            success = await step()
            if not success:
                await self.ctx.send("❌ Setup cancelled or failed!")
                return
                
        await self.ctx.send("✅ Setup completed successfully!")

    async def setup_channels(self):
        embed = discord.Embed(
            title="📺 Step 1: Channel Setup",
            description="I'll create the necessary channels for Cookie Bot.",
            color=0x5865f2
        )
        embed.add_field(
            name="Channels to create:",
            value=(
                "• 🍪 cookie-claims\n"
                "• 📸 feedback-photos\n"
                "• 📝 bot-logs\n"
                "• 📢 announcements\n"
                "• 🎮 games-room\n"
                "• 📊 analytics"
            ),
            inline=False
        )
        
        view = ChannelSetupView(self.ctx)
        msg = await self.ctx.send(embed=embed, view=view)
        
        await view.wait()
        if view.cancelled:
            return False
            
        self.setup_data["channels"] = view.channels_created
        return True
    
    async def setup_roles(self):
        embed = discord.Embed(
            title="🎭 Step 2: Role Setup",
            description="Configure roles with specific cookie access and benefits.",
            color=0x5865f2
        )
        
        config = await bot.db.config.find_one({"_id": "bot_config"})
        view = RoleSetupView(self.ctx, config or {})
        msg = await self.ctx.send(embed=embed, view=view)
        
        await view.wait()
        self.setup_data["roles"] = view.roles_created
        return True
    
    async def configure_cookies(self):
        embed = discord.Embed(
            title="🍪 Step 3: Cookie Configuration",
            description="Setting up cookie types with role-based access.",
            color=0x5865f2
        )
        
        config = await bot.db.config.find_one({"_id": "bot_config"})
        if config and "default_cookies" in config:
            self.setup_data["cookies"] = config["default_cookies"]
            
            cookies_list = "\n".join([
                f"• **{cookie.title()}** - {cfg['description']}" 
                for cookie, cfg in config["default_cookies"].items()
            ])
            
            embed.add_field(
                name="✅ Cookies Configured",
                value=cookies_list[:1024],
                inline=False
            )
        else:
            embed.add_field(
                name="⚠️ Warning",
                value="Default cookie configuration not found. Run database setup first!",
                inline=False
            )
            
        await self.ctx.send(embed=embed)
        await asyncio.sleep(3)
        return True
    
    async def configure_games(self):
        embed = discord.Embed(
            title="🎮 Step 4: Games Configuration",
            description="Enable entertainment features for your server.",
            color=0x5865f2
        )
        
        games_config = {
            "enabled": True,
            "channel_required": True,
            "games_config": {
                "slots": {"enabled": True, "custom_settings": {}},
                "bet": {"enabled": True, "custom_settings": {}},
                "rob": {"enabled": True, "custom_settings": {}},
                "gamble": {"enabled": True, "custom_settings": {}},
                "giveaway": {"enabled": True, "custom_settings": {}}
            }
        }
        
        self.setup_data["games"] = games_config
        
        embed.add_field(
            name="🎰 Available Games",
            value=(
                "• **Slots** - Classic slot machine\n"
                "• **Bet** - Number guessing game\n"
                "• **Rob** - Steal points from others\n"
                "• **Divine Gamble** - Ultimate risk/reward\n"
                "• **Giveaway** - Points giveaways"
            ),
            inline=False
        )
        
        await self.ctx.send(embed=embed)
        await asyncio.sleep(3)
        return True
    
    async def configure_settings(self):
        self.setup_data["settings"] = {
            "feedback_required": True,
            "feedback_timeout": 15,
            "max_daily_claims": 10,
            "blacklist_after_warnings": 3,
            "invite_tracking": True,
            "analytics_enabled": True,
            "role_hierarchy_enabled": True,
            "daily_claim_tracking": True
        }
        
        embed = discord.Embed(
            title="⚙️ Step 5: Bot Settings",
            description="Configured settings:",
            color=0x5865f2
        )
        
        for key, value in self.setup_data["settings"].items():
            embed.add_field(
                name=key.replace("_", " ").title(),
                value=str(value),
                inline=True
            )
            
        await self.ctx.send(embed=embed)
        await asyncio.sleep(2)
        return True
    
    async def finalize_setup(self):
        embed = discord.Embed(
            title="💾 Finalizing Setup...",
            description="Saving configuration to database...",
            color=0x5865f2
        )
        msg = await self.ctx.send(embed=embed)
        
        server_data = {
            "server_id": self.ctx.guild.id,
            "server_name": self.ctx.guild.name,
            "owner_id": self.ctx.guild.owner_id,
            "channels": self.setup_data["channels"],
            "cookies": self.setup_data["cookies"],
            "role_based": True,
            "roles": self.setup_data["roles"],
            "games": self.setup_data["games"],
            "enabled": True,
            "setup_complete": True,
            "settings": self.setup_data["settings"],
            "premium_tier": "basic",
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc)
        }
        
        await bot.db.servers.update_one(
            {"server_id": self.ctx.guild.id},
            {"$set": server_data},
            upsert=True
        )
        
        embed = discord.Embed(
            title="✅ Setup Complete!",
            description="Your server is now configured!",
            color=0x00ff00
        )
        
        cookie_channel_id = self.setup_data["channels"].get("cookie")
        if cookie_channel_id:
            cookie_channel = bot.get_channel(cookie_channel_id)
            if cookie_channel:
                await send_welcome_message(cookie_channel)
                embed.add_field(
                    name="🍪 Cookie Channel",
                    value=f"Welcome message sent to {cookie_channel.mention}",
                    inline=False
                )
        
        await msg.edit(embed=embed)
        return True

class ChannelSetupView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.channels_created = {}
        self.cancelled = False
        
    @discord.ui.button(label="Create Channels", style=discord.ButtonStyle.success, emoji="✅")
    async def create_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the setup initiator can use this!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        guild = self.ctx.guild
        category_name = "🍪 Cookie Bot"
        
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(
                category_name,
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(
                        send_messages=False,
                        add_reactions=True,
                        read_messages=True
                    ),
                    guild.me: discord.PermissionOverwrite(
                        send_messages=True,
                        manage_channels=True,
                        manage_messages=True,
                        embed_links=True,
                        attach_files=True,
                        add_reactions=True
                    )
                }
            )
        
        channel_configs = [
            {
                "name": "🍪cookie-claims",
                "topic": "Use /cookie to claim cookies here! Check /help for commands.",
                "type": "cookie",
                "slowmode": 5
            },
            {
                "name": "📸feedback-photos",
                "topic": "Submit your cookie feedback with screenshots within 15 minutes!",
                "type": "feedback",
                "slowmode": 0
            },
            {
                "name": "📝bot-logs",
                "topic": "Bot activity, moderation logs, and system messages",
                "type": "log",
                "private": True
            },
            {
                "name": "📢announcements",
                "topic": "Important updates, events, and new features",
                "type": "announcement",
                "announcement": True
            },
            {
                "name": "🎮games-room",
                "topic": "Play games like slots, betting, and more!",
                "type": "games",
                "slowmode": 3
            },
            {
                "name": "📊analytics",
                "topic": "Server statistics and performance metrics",
                "type": "analytics",
                "private": True
            }
        ]
        
        embed = discord.Embed(
            title="Creating Channels...",
            color=0x5865f2
        )
        
        for config in channel_configs:
            channel = discord.utils.get(category.channels, name=config["name"])
            
            if not channel:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        send_messages=False if config.get("private") else True,
                        read_messages=False if config.get("private") else True
                    ),
                    guild.me: discord.PermissionOverwrite(
                        send_messages=True,
                        manage_messages=True,
                        embed_links=True
                    )
                }
                
                channel = await category.create_text_channel(
                    config["name"],
                    topic=config["topic"],
                    overwrites=overwrites,
                    slowmode_delay=config.get("slowmode", 0)
                )
                
                embed.add_field(
                    name=config["name"],
                    value="✅ Created",
                    inline=True
                )
            else:
                embed.add_field(
                    name=config["name"],
                    value="✓ Exists",
                    inline=True
                )
            
            self.channels_created[config["type"]] = channel.id
        
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=None
        )
        self.stop()
        
    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the setup initiator can use this!", ephemeral=True)
            return
            
        await interaction.response.edit_message(
            content="⏭️ Skipped channel creation",
            embed=None,
            view=None
        )
        self.stop()
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the setup initiator can use this!", ephemeral=True)
            return
            
        self.cancelled = True
        await interaction.response.edit_message(
            content="❌ Setup cancelled",
            embed=None,
            view=None
        )
        self.stop()

class RoleSetupView(discord.ui.View):
    def __init__(self, ctx, bot_config):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot_config = bot_config
        self.roles_created = {}
        
    @discord.ui.select(
        placeholder="Select roles to create/configure...",
        min_values=1,
        max_values=7,
        options=[
            discord.SelectOption(label="Free Cookie", value="free", emoji="🆓", 
                               description="Basic access with limited cookies"),
            discord.SelectOption(label="Premium Cookie", value="premium", emoji="⭐", 
                               description="Enhanced access with reduced costs"),
            discord.SelectOption(label="VIP Cookie", value="vip", emoji="💎", 
                               description="VIP access with major discounts"),
            discord.SelectOption(label="Elite Cookie", value="elite", emoji="🎯", 
                               description="Elite access with minimal costs"),
            discord.SelectOption(label="Staff Cookie", value="staff", emoji="🛡️", 
                               description="Staff members special privileges"),
            discord.SelectOption(label="Booster Role", value="booster", emoji="🚀", 
                               description="Configure server booster benefits"),
            discord.SelectOption(label="Cookie Blacklist", value="blacklist", emoji="🚫", 
                               description="Blacklisted users role")
        ]
    )
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the setup initiator can use this!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        guild = self.ctx.guild
        role_configs = {
            "free": ("🆓 Free Cookie", discord.Color.default()),
            "premium": ("⭐ Premium Cookie", discord.Color.gold()),
            "vip": ("💎 VIP Cookie", discord.Color.purple()),
            "elite": ("🎯 Elite Cookie", discord.Color.dark_blue()),
            "staff": ("🛡️ Staff Cookie", discord.Color.red()),
            "blacklist": ("🚫 Cookie Blacklist", discord.Color.dark_red())
        }
        
        embed = discord.Embed(
            title="Creating/Configuring Roles...",
            color=0x5865f2
        )
        
        default_roles = self.bot_config.get("default_roles", {})
        
        for value in select.values:
            if value == "booster":
                if guild.premium_subscriber_role:
                    booster_config = default_roles.get("booster", {})
                    self.roles_created[str(guild.premium_subscriber_role.id)] = booster_config
                    embed.add_field(
                        name="🚀 Server Booster",
                        value="✅ Configured with perks",
                        inline=True
                    )
                continue
                
            role_name, color = role_configs[value]
            role = discord.utils.get(guild.roles, name=role_name)
            
            if not role:
                role = await guild.create_role(
                    name=role_name,
                    color=color,
                    mentionable=False,
                    hoist=True if value in ["premium", "vip", "elite", "staff"] else False
                )
                embed.add_field(
                    name=role_name,
                    value="✅ Created",
                    inline=True
                )
            else:
                embed.add_field(
                    name=role_name,
                    value="✓ Exists",
                    inline=True
                )
            
            if value != "blacklist":
                default_config = default_roles.get(value, {})
                self.roles_created[str(role.id)] = default_config
        
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=None
        )
        self.stop()

@bot.event
async def on_ready():
    print(f"🚀 Setup Wizard Online: {bot.user}")
    print(f"📊 Connected to {len(bot.guilds)} servers")
    
    bot.config = await bot.db.config.find_one({"_id": "bot_config"})
    if not bot.config:
        print("⚠️ Bot config not found! Run db_setup.py first!")
        
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")

@bot.hybrid_command(name="setup", description="Run the interactive setup wizard")
@commands.has_permissions(administrator=True)
async def setup_wizard(ctx):
    existing = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    
    embed = discord.Embed(
        title="🍪 Cookie Bot Setup Wizard",
        description=(
            "Welcome to the Cookie Bot setup wizard!\n\n"
            "**Features:**\n"
            "• Dynamic role-based cookie access\n"
            "• Game configurations\n"
            "• Daily claim limits per cookie\n"
            "• Trust multipliers by role\n"
            "• Enhanced analytics\n\n"
            "This wizard will guide you through:\n"
            "• Creating necessary channels\n"
            "• Setting up roles with specific benefits\n"
            "• Configuring cookie types\n"
            "• Enabling games\n"
            "• Customizing bot settings\n\n"
            "Click **Start Setup** to begin!"
        ),
        color=0x5865f2,
        timestamp=datetime.now(timezone.utc)
    )
    
    if existing:
        embed.add_field(
            name="⚠️ Existing Setup Detected",
            value="Running setup will update to the latest configuration.",
            inline=False
        )
    
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="Setup Wizard v2.1")
    
    view = SetupWizardView(ctx)
    await ctx.send(embed=embed, view=view)

@bot.hybrid_command(name="quicksetup", description="Quick setup with defaults")
@commands.has_permissions(administrator=True)
async def quick_setup(ctx):
    await ctx.defer()
    
    guild = ctx.guild
    embed = discord.Embed(
        title="⚡ Quick Setup in Progress...",
        color=0x5865f2
    )
    status_msg = await ctx.send(embed=embed)
    
    config = bot.config or await bot.db.config.find_one({"_id": "bot_config"})
    if not config:
        await ctx.send("❌ Bot configuration not found! Run db_setup.py first.")
        return
    
    category = await create_category(guild)
    channels = await create_channels(guild, category)
    roles = await create_roles(guild, config)
    
    server_data = {
        "server_id": guild.id,
        "server_name": guild.name,
        "owner_id": guild.owner_id,
        "channels": channels,
        "cookies": config["default_cookies"],
        "role_based": True,
        "roles": roles,
        "games": {
            "enabled": True,
            "channel_required": True,
            "games_config": {
                "slots": {"enabled": True, "custom_settings": {}},
                "bet": {"enabled": True, "custom_settings": {}},
                "rob": {"enabled": True, "custom_settings": {}},
                "gamble": {"enabled": True, "custom_settings": {}},
                "giveaway": {"enabled": True, "custom_settings": {}}
            }
        },
        "enabled": True,
        "setup_complete": True,
        "settings": {
            "feedback_required": True,
            "feedback_timeout": 15,
            "max_daily_claims": 10,
            "blacklist_after_warnings": 3,
            "invite_tracking": True,
            "analytics_enabled": True,
            "role_hierarchy_enabled": True,
            "daily_claim_tracking": True
        },
        "premium_tier": "basic",
        "created_at": datetime.now(timezone.utc),
        "last_updated": datetime.now(timezone.utc)
    }
    
    await bot.db.servers.update_one(
        {"server_id": guild.id},
        {"$set": server_data},
        upsert=True
    )
    
    final_embed = discord.Embed(
        title="✅ Quick Setup Complete!",
        description="Your server is now ready with all features!",
        color=0x00ff00,
        timestamp=datetime.now(timezone.utc)
    )
    
    final_embed.add_field(
        name="📺 Channels",
        value=f"Created {len(channels)} channels",
        inline=True
    )
    final_embed.add_field(
        name="🎭 Roles",
        value=f"Configured {len(roles)} roles",
        inline=True
    )
    final_embed.add_field(
        name="🍪 Cookies",
        value=f"{len(config['default_cookies'])} types available",
        inline=True
    )
    final_embed.add_field(
        name="🎮 Games",
        value="All games enabled",
        inline=True
    )
    
    final_embed.add_field(
        name="✨ Features",
        value=(
            "• Role-specific cookie access\n"
            "• Daily claim limits per role\n"
            "• Trust score multipliers\n"
            "• Game bonuses by role\n"
            "• Enhanced analytics"
        ),
        inline=False
    )
    
    final_embed.add_field(
        name="📋 Next Steps",
        value=(
            "1. Add cookie files to your directories\n"
            "2. Configure role benefits with `/roleconfig`\n"
            "3. Check `/help` for all commands\n"
            "4. Test games in the games channel\n"
            "5. Join our support server for help!"
        ),
        inline=False
    )
    
    await status_msg.edit(embed=final_embed)
    
    cookie_channel_id = channels.get("cookie")
    if cookie_channel_id:
        cookie_channel = bot.get_channel(cookie_channel_id)
        if cookie_channel:
            await send_welcome_message(cookie_channel)
            
    games_channel_id = channels.get("games")
    if games_channel_id:
        games_channel = bot.get_channel(games_channel_id)
        if games_channel:
            await send_games_welcome_message(games_channel)

async def create_category(guild):
    category_name = "🍪 Cookie Bot"
    category = discord.utils.get(guild.categories, name=category_name)
    
    if not category:
        category = await guild.create_category(
            category_name,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False,
                    add_reactions=True,
                    read_messages=True
                ),
                guild.me: discord.PermissionOverwrite(
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True,
                    embed_links=True,
                    attach_files=True
                )
            }
        )
    
    return category

async def create_channels(guild, category):
    channels_created = {}
    
    channel_configs = [
        ("🍪cookie-claims", "cookie", False),
        ("📸feedback-photos", "feedback", False),
        ("📝bot-logs", "log", True),
        ("📢announcements", "announcement", False),
        ("🎮games-room", "games", False),
        ("📊analytics", "analytics", True)
    ]
    
    for name, ch_type, private in channel_configs:
        channel = discord.utils.get(category.channels, name=name)
        
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False if private else True,
                    read_messages=False if private else True
                ),
                guild.me: discord.PermissionOverwrite(
                    send_messages=True,
                    manage_messages=True,
                    embed_links=True
                )
            }
            
            channel = await category.create_text_channel(
                name,
                overwrites=overwrites,
                slowmode_delay=3 if ch_type == "games" else 0
            )
        
        channels_created[ch_type] = channel.id
    
    return channels_created

async def create_roles(guild, config):
    roles_created = {}
    default_roles = config.get("default_roles", {})
    
    role_configs = [
        ("🆓 Free Cookie", discord.Color.default(), "free"),
        ("⭐ Premium Cookie", discord.Color.gold(), "premium"),
        ("💎 VIP Cookie", discord.Color.purple(), "vip"),
        ("🎯 Elite Cookie", discord.Color.dark_blue(), "elite"),
        ("🛡️ Staff Cookie", discord.Color.red(), "staff")
    ]
    
    for role_name, color, role_type in role_configs:
        role = discord.utils.get(guild.roles, name=role_name)
        
        if not role:
            role = await guild.create_role(
                name=role_name,
                color=color,
                mentionable=False,
                hoist=role_type != "free"
            )
        
        roles_created[str(role.id)] = default_roles.get(role_type, {})
    
    if guild.premium_subscriber_role:
        roles_created[str(guild.premium_subscriber_role.id)] = default_roles.get("booster", {})
    
    return roles_created

async def send_welcome_message(channel):
    embed = discord.Embed(
        title="🍪 Welcome to Cookie Bot Premium!",
        description=(
            "Your premium cookie distribution system is ready!\n\n"
            "**🚀 Features:**\n"
            "• Role-based cookie access\n"
            "• Daily claim limits\n"
            "• Trust score multipliers\n"
            "• Entertainment games\n"
            "• Enhanced analytics\n\n"
            "**📋 Getting Started:**"
        ),
        color=0x5865f2,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.add_field(
        name="📋 Basic Commands",
        value=(
            "`/cookie` - Claim a cookie\n"
            "`/daily` - Get daily points\n"
            "`/points` - Check balance\n"
            "`/help` - All commands\n"
            "`/games` - View games"
        ),
        inline=True
    )
    
    embed.add_field(
        name="🍪 Cookie Types",
        value=(
            "Netflix • Spotify • Prime\n"
            "ChatGPT • Claude • Trading\n"
            "And many more!"
        ),
        inline=True
    )
    
    embed.add_field(
        name="🎭 Role Benefits",
        value=(
            "• **Free**: Basic access\n"
            "• **Premium**: Lower costs\n"
            "• **VIP**: Major discounts\n"
            "• **Elite**: Minimal costs\n"
            "• **Booster**: Amazing perks!"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Important Rules",
        value=(
            "• Submit feedback in **15 minutes**\n"
            "• Include screenshots in feedback\n"
            "• Enable DMs to receive cookies\n"
            "• No feedback = **30 day blacklist**\n"
            "• Check your daily limits per role"
        ),
        inline=False
    )
    
    embed.set_footer(text="Cookie Bot v2.1 | Premium Features Enabled")
    
    await channel.send(embed=embed)

async def send_games_welcome_message(channel):
    embed = discord.Embed(
        title="🎮 Welcome to the Games Room!",
        description=(
            "Test your luck and earn or lose points!\n\n"
            "**Available Games:**"
        ),
        color=0x9b59b6
    )
    
    embed.add_field(
        name="🎰 Slots",
        value="`/slots play <amount>` - Classic slot machine\nMin: 5, Max: 200 points",
        inline=False
    )
    
    embed.add_field(
        name="🎲 Betting",
        value="`/bet solo/group points` - Number guessing game\nSolo or multiplayer modes",
        inline=False
    )
    
    embed.add_field(
        name="🎭 Robbing",
        value="`/rob @user` - Steal points from others\nSuccess based on trust scores",
        inline=False
    )
    
    embed.add_field(
        name="🎰 Divine Gamble",
        value="`/gamble divine` - Ultimate risk (5% win chance)\nMassive rewards or curse",
        inline=False
    )
    
    embed.add_field(
        name="🎁 Giveaways",
        value="Watch for point giveaways hosted by the owner!",
        inline=False
    )
    
    embed.set_footer(text="Remember: The house always wins! Gamble responsibly.")
    
    await channel.send(embed=embed)

@bot.hybrid_command(name="roleconfig", description="Configure specific role benefits")
@commands.has_permissions(administrator=True)
async def role_config(ctx, role: discord.Role):
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    if not server:
        await ctx.send("❌ Please run `/setup` first!")
        return
        
    config = await bot.db.config.find_one({"_id": "bot_config"})
    default_roles = config.get("default_roles", {})
    
    embed = discord.Embed(
        title=f"🎭 Configure {role.name}",
        description="Current configuration:",
        color=role.color
    )
    
    role_data = server.get("roles", {}).get(str(role.id), {})
    
    embed.add_field(
        name="General Benefits",
        value=(
            f"Daily Bonus: {role_data.get('daily_bonus', 0)} points\n"
            f"Trust Multiplier: {role_data.get('trust_multiplier', 1.0)}x\n"
            f"Game Benefits: {role_data.get('game_benefits', {}).get('slots_max_bet_bonus', 0)} slots bonus"
        ),
        inline=False
    )
    
    if "cookie_access" in role_data:
        cookie_text = []
        for cookie, access in list(role_data["cookie_access"].items())[:5]:
            if access.get("enabled"):
                cookie_text.append(
                    f"**{cookie}**: {access['cost']} pts, {access['cooldown']}h CD, {access['daily_limit']} daily"
                )
        
        embed.add_field(
            name="Cookie Access",
            value="\n".join(cookie_text) or "No specific cookie configuration",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="config", description="Configure bot settings")
@commands.has_permissions(administrator=True)
async def config_command(ctx):
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    
    if not server:
        await ctx.send("❌ Please run `/setup` first!")
        return
    
    embed = discord.Embed(
        title="⚙️ Server Configuration",
        description=f"Settings for **{ctx.guild.name}**",
        color=0x5865f2,
        timestamp=datetime.now(timezone.utc)
    )
    
    settings = server.get("settings", {})
    embed.add_field(
        name="📋 Current Settings",
        value=(
            f"Feedback Required: {'✅' if settings.get('feedback_required', True) else '❌'}\n"
            f"Feedback Timeout: {settings.get('feedback_timeout', 15)} minutes\n"
            f"Max Daily Claims: {settings.get('max_daily_claims', 10)}\n"
            f"Blacklist Warnings: {settings.get('blacklist_after_warnings', 3)}\n"
            f"Role-based System: {'✅' if server.get('role_based', True) else '❌'}"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 Statistics",
        value=(
            f"Cookie Types: {len(server.get('cookies', {}))}\n"
            f"Configured Roles: {len(server.get('roles', {}))}\n"
            f"Premium Tier: {server.get('premium_tier', 'basic').title()}"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔧 Configuration Commands",
        value=(
            "`/setsetting <setting> <value>` - Change a setting\n"
            "`/toggle <feature>` - Toggle features on/off\n"
            "`/setcookie <type> <cost> <cooldown>` - Configure cookies\n"
            "`/setrole <role> <benefits>` - Configure role benefits"
        ),
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="help", description="Show all commands and features")
async def help_command(ctx):
    embed = discord.Embed(
        title="🍪 Cookie Bot Help Center",
        description="Everything you need to know about Cookie Bot!",
        color=0x5865f2,
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.add_field(
        name="👨‍💼 Admin Commands",
        value=(
            "`/setup` - Interactive setup wizard\n"
            "`/quicksetup` - Quick setup with defaults\n"
            "`/roleconfig` - Configure role benefits\n"
            "`/config` - View/change settings\n"
            "`/toggle` - Enable/disable features"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👤 User Commands",
        value=(
            "`/cookie` - Claim a cookie\n"
            "`/daily` - Get daily points + role bonus\n"
            "`/points` - Check your balance\n"
            "`/status` - View detailed status\n"
            "`/stock` - Check cookie availability\n"
            "`/feedback` - Submit feedback\n"
            "`/invites` - Check invite stats\n"
            "`/refresh` - Refresh role benefits"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎮 Game Commands",
        value=(
            "`/games` - View all games guide\n"
            "`/slots play` - Play slot machine\n"
            "`/bet` - Start a betting game\n"
            "`/rob` - Rob another user\n"
            "`/gamble divine` - Divine gamble"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎭 Role Benefits",
        value=(
            "• Daily bonus points\n"
            "• Lower cookie costs\n"
            "• Reduced cooldowns\n"
            "• Higher daily limits\n"
            "• Trust multipliers\n"
            "• Game bonuses"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📚 Resources",
        value=(
            "[Support Server](https://discord.gg/your-invite)\n"
            "[Documentation](https://docs.cookiebot.com)\n"
            "[Premium](https://cookiebot.com/premium)"
        ),
        inline=False
    )
    
    embed.set_footer(text="Cookie Bot v2.1")
    
    await ctx.send(embed=embed)

bot.run(BOT_TOKEN)