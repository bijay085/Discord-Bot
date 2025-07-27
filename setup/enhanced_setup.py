# setup/enhanced_setup.py

import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path

load_dotenv()

class SetupBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.remove_command("help")
        self.db = None

bot = SetupBot()

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "1192694890530869369"))
MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "1348916338961154088"))
MAIN_SERVER_INVITE = os.getenv("MAIN_SERVER_INVITE", "https://discord.gg/WVq522fsr3")

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
bot.db = mongo_client[DATABASE_NAME]

def is_owner_or_admin():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
        if server and ctx.author.id in server.get("admins", []):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        return False
    return commands.check(predicate)

class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.setup_complete = False
        
    @discord.ui.button(label="📋 Basic Setup", style=discord.ButtonStyle.primary, row=0)
    async def basic_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ctx = await bot.get_context(interaction.message)
        await setup_basic(ctx)
        
    @discord.ui.button(label="🎭 Setup Roles", style=discord.ButtonStyle.secondary, row=0)
    async def setup_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ctx = await bot.get_context(interaction.message)
        await setup_roles_cmd(ctx)
        
    @discord.ui.button(label="🍪 Configure Cookies", style=discord.ButtonStyle.secondary, row=0)
    async def configure_cookies(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ctx = await bot.get_context(interaction.message)
        await configure_cookies(ctx)
        
    @discord.ui.button(label="✅ Complete Setup", style=discord.ButtonStyle.success, row=1)
    async def complete_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.setup_complete = True
        await interaction.response.edit_message(
            content="✅ Setup completed! Use `/help` to get started.",
            view=None
        )
        self.stop()

@bot.event
async def on_ready():
    print(f"🚀 Setup Bot Online: {bot.user}")
    print(f"📊 Connected to {len(bot.guilds)} servers")
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")

@bot.event
async def on_guild_join(guild):
    print(f"📥 Joined: {guild.name} ({guild.id})")
    
    embed = discord.Embed(
        title="🍪 Cookie Bot Setup Required",
        description=(
            "Thanks for adding Cookie Bot! Let's get started.\n\n"
            "**Quick Setup:**\n"
            "• An admin needs to run `!setup`\n"
            "• This will create channels and roles\n"
            "• Configure your preferences\n\n"
            "**Support:**\n"
            f"• [Join our server]({MAIN_SERVER_INVITE})\n"
            "• Use `!help` for commands"
        ),
        color=0x5865f2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)
            break

@bot.command(name="setup")
@is_owner_or_admin()
async def setup_server(ctx):
    embed = discord.Embed(
        title="🔧 Cookie Bot Setup Wizard",
        description="Welcome to the setup wizard! Choose your setup options:",
        color=0x5865f2
    )
    embed.add_field(
        name="📋 Basic Setup",
        value="Creates channels and basic configuration",
        inline=False
    )
    embed.add_field(
        name="🎭 Setup Roles", 
        value="Configure role-based benefits",
        inline=False
    )
    embed.add_field(
        name="🍪 Configure Cookies",
        value="Set up cookie types and directories",
        inline=False
    )
    
    view = SetupView()
    await ctx.send(embed=embed, view=view)

async def setup_basic(ctx):
    guild = ctx.guild
    status_embed = discord.Embed(
        title="⏳ Running Basic Setup...",
        color=0x5865f2
    )
    status_msg = await ctx.send(embed=status_embed)
    
    # Check for existing setup
    existing = await bot.db.servers.find_one({"server_id": guild.id})
    
    # Create or get category
    category_name = "🍪 Cookie Bot"
    existing_category = discord.utils.get(guild.categories, name=category_name)
    
    if existing_category:
        category = existing_category
        status_embed.add_field(name="📁 Category", value="✅ Using existing", inline=True)
    else:
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
        status_embed.add_field(name="📁 Category", value="✅ Created", inline=True)
    
    await status_msg.edit(embed=status_embed)
    
    # Create channels
    channels_created = {}
    channel_configs = [
        {
            "name": "🍪cookie-claims",
            "topic": "Use `/cookie` to claim cookies here!",
            "type": "cookie",
            "overwrites": {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=True,
                    read_messages=True
                )
            }
        },
        {
            "name": "📸feedback-photos",
            "topic": "Submit your cookie feedback with screenshots",
            "type": "feedback",
            "overwrites": {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=True,
                    attach_files=True,
                    read_messages=True
                )
            }
        },
        {
            "name": "📝bot-logs",
            "topic": "Bot activity and moderation logs",
            "type": "log",
            "overwrites": {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False,
                    read_messages=False
                )
            }
        },
        {
            "name": "📢announcements",
            "topic": "Bot updates and events",
            "type": "announcement",
            "overwrites": {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False,
                    read_messages=True
                )
            }
        },
        {
            "name": "📊analytics",
            "topic": "Server statistics and analytics",
            "type": "analytics",
            "overwrites": {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False,
                    read_messages=False
                )
            }
        }
    ]
    
    for ch_config in channel_configs:
        channel = discord.utils.get(category.channels, name=ch_config["name"])
        if not channel:
            channel = await category.create_text_channel(
                ch_config["name"],
                topic=ch_config["topic"],
                overwrites=ch_config["overwrites"]
            )
            status_embed.add_field(
                name=f"#{ch_config['name']}", 
                value="✅ Created", 
                inline=True
            )
        else:
            status_embed.add_field(
                name=f"#{ch_config['name']}", 
                value="✅ Exists", 
                inline=True
            )
        
        channels_created[ch_config["type"]] = channel.id
    
    await status_msg.edit(embed=status_embed)
    
    # Get default configurations
    config = await bot.db.config.find_one({"_id": "bot_config"})
    if not config:
        await initialize_bot_config()
        config = await bot.db.config.find_one({"_id": "bot_config"})
    
    default_cookies = config.get("default_cookies", {})
    
    # Create base directory if it doesn't exist
    base_dir = "D:/Discord Bot/cookies"
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    
    # Update directories for this server
    server_cookies = {}
    for cookie_type, cookie_config in default_cookies.items():
        server_dir = f"{base_dir}/{guild.id}/{cookie_type}"
        Path(server_dir).mkdir(parents=True, exist_ok=True)
        
        server_cookies[cookie_type] = {
            **cookie_config,
            "directory": server_dir
        }
    
    # Save server configuration
    server_data = {
        "server_id": guild.id,
        "server_name": guild.name,
        "invite_link": None,
        "server_owner": guild.owner_id,
        "admins": [guild.owner_id, OWNER_ID],
        "channels": channels_created,
        "cookies": server_cookies,
        "role_based": True,
        "roles": {},
        "whitelist_mode": False,
        "whitelisted_servers": [],
        "enabled": True,
        "premium_features": {
            "custom_cookies": False,
            "advanced_analytics": False,
            "priority_support": False
        },
        "settings": {
            "feedback_required": True,
            "feedback_timeout": 15,
            "max_daily_claims": 10,
            "blacklist_after_warnings": 3
        },
        "created_at": datetime.now(timezone.utc)
    }
    
    await bot.db.servers.update_one(
        {"server_id": guild.id},
        {"$set": server_data},
        upsert=True
    )
    
    # Final summary
    final_embed = discord.Embed(
        title="✅ Basic Setup Complete!",
        description="Your server is now configured with basic settings.",
        color=0x00ff00,
        timestamp=datetime.now(timezone.utc)
    )
    final_embed.add_field(
        name="📋 Next Steps",
        value=(
            "• Run `!setup_roles` to configure role benefits\n"
            "• Run `!addcookie` to add custom cookie types\n"
            "• Use `/help` to see all commands"
        ),
        inline=False
    )
    final_embed.add_field(
        name="🔗 Important Links",
        value=(
            f"• [Support Server]({MAIN_SERVER_INVITE})\n"
            "• [Documentation](https://cookiebot.com/docs)\n"
            "• [Premium](https://cookiebot.com/premium)"
        ),
        inline=False
    )
    
    await status_msg.edit(embed=final_embed)
    
    # Send welcome message in cookie channel
    cookie_channel = bot.get_channel(channels_created.get("cookie"))
    if cookie_channel:
        welcome_embed = discord.Embed(
            title="🍪 Welcome to Cookie Bot!",
            description=(
                "**How to get started:**\n"
                "1️⃣ Use `/daily` to claim free points\n"
                "2️⃣ Use `/cookie` to claim cookies\n"
                "3️⃣ Submit feedback within 15 minutes\n"
                "4️⃣ Check `/help` for all commands\n\n"
                "**Available Cookie Types:**\n"
                "🎬 Netflix • 🎵 Spotify • 📦 Prime • ⭐ JioHotstar\n"
                "📈 TradingView • 🤖 ChatGPT • 🧠 Claude • 🦚 Peacock\n"
                "🍙 Crunchyroll • 📺 CanalPlus\n\n"
                "**Important:** Always submit feedback or risk blacklist!"
            ),
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        welcome_embed.set_image(url="https://i.imgur.com/YourImageHere.png")  # Add your banner
        welcome_embed.set_footer(text="Cookie Bot v2.0", icon_url=bot.user.display_avatar.url)
        
        await cookie_channel.send(embed=welcome_embed)
    
    # Log the setup
    log_channel = bot.get_channel(channels_created.get("log"))
    if log_channel:
        log_embed = discord.Embed(
            title="🔧 Server Setup Completed",
            description=f"Setup completed by {ctx.author.mention}",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Channels", value=len(channels_created), inline=True)
        log_embed.add_field(name="Cookies", value=len(server_cookies), inline=True)
        log_embed.add_field(name="Status", value="✅ Active", inline=True)
        
        await log_channel.send(embed=log_embed)

@bot.command(name="setup_roles")
@is_owner_or_admin()
async def setup_roles_cmd(ctx):
    guild = ctx.guild
    
    embed = discord.Embed(
        title="🎭 Setting up Roles...",
        description="Creating role hierarchy with benefits",
        color=0x5865f2
    )
    status_msg = await ctx.send(embed=embed)
    
    roles_created = {}
    role_configs = [
        {
            "name": "🍪 Free Cookie",
            "color": discord.Color.default(),
            "key": "free",
            "position": 1,
            "config": {
                "cooldown": 72,
                "cost": "default",
                "access": ["netflix", "spotify", "prime"],
                "daily_bonus": 0
            }
        },
        {
            "name": "⭐ Premium Cookie",
            "color": discord.Color.gold(),
            "key": "premium",
            "position": 2,
            "config": {
                "cooldown": 24,
                "cost": 2,
                "access": ["all"],
                "daily_bonus": 5
            }
        },
        {
            "name": "💎 VIP Cookie",
            "color": discord.Color.purple(),
            "key": "vip",
            "position": 3,
            "config": {
                "cooldown": 12,
                "cost": 1,
                "access": ["all"],
                "daily_bonus": 10
            }
        },
        {
            "name": "🎯 Elite Cookie",
            "color": discord.Color.dark_blue(),
            "key": "elite",
            "position": 4,
            "config": {
                "cooldown": 6,
                "cost": 0,
                "access": ["all"],
                "daily_bonus": 20
            }
        },
        {
            "name": "🛡️ Staff Cookie",
            "color": discord.Color.red(),
            "key": "staff",
            "position": 5,
            "config": {
                "cooldown": 0,
                "cost": 0,
                "access": ["all"],
                "daily_bonus": 50
            }
        },
        {
            "name": "🚫 Cookie Blacklist",
            "color": discord.Color.dark_red(),
            "key": "blacklist",
            "position": 0,
            "config": None
        }
    ]
    
    for role_config in role_configs:
        role = discord.utils.get(guild.roles, name=role_config["name"])
        if not role:
            role = await guild.create_role(
                name=role_config["name"],
                color=role_config["color"],
                mentionable=False,
                hoist=True if role_config["position"] > 2 else False
            )
            embed.add_field(
                name=role_config["name"],
                value="✅ Created",
                inline=True
            )
        else:
            embed.add_field(
                name=role_config["name"],
                value="✅ Exists",
                inline=True
            )
        
        if role_config["config"]:
            roles_created[str(role.id)] = {
                "name": role_config["key"],
                **role_config["config"]
            }
    
    await status_msg.edit(embed=embed)
    
    # Handle booster role
    if guild.premium_subscriber_role:
        roles_created[str(guild.premium_subscriber_role.id)] = {
            "name": "booster",
            "cooldown": 0,
            "cost": 0,
            "access": ["all"],
            "daily_bonus": 100
        }
        embed.add_field(
            name="🚀 Server Booster",
            value="✅ Configured",
            inline=True
        )
        await status_msg.edit(embed=embed)
    
    # Create special roles
    special_roles = [
        {
            "name": "🎉 Event Winner",
            "color": discord.Color.from_rgb(255, 215, 0),
            "config": {
                "cooldown": 48,
                "cost": 3,
                "access": ["all"],
                "daily_bonus": 15
            }
        },
        {
            "name": "👑 Cookie King",
            "color": discord.Color.from_rgb(255, 223, 0),
            "config": {
                "cooldown": 24,
                "cost": 1,
                "access": ["all"],
                "daily_bonus": 25
            }
        }
    ]
    
    for special in special_roles:
        role = discord.utils.get(guild.roles, name=special["name"])
        if not role:
            role = await guild.create_role(
                name=special["name"],
                color=special["color"],
                mentionable=True,
                hoist=True
            )
        
        roles_created[str(role.id)] = {
            "name": special["name"].lower().replace(" ", "_"),
            **special["config"]
        }
    
    # Update server configuration
    await bot.db.servers.update_one(
        {"server_id": guild.id},
        {"$set": {"roles": roles_created}}
    )
    
    # Final summary
    final_embed = discord.Embed(
        title="✅ Role Setup Complete!",
        description=f"Created/configured **{len(roles_created)}** roles",
        color=0x00ff00,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Add role benefits summary
    benefits_text = ""
    for role_id, config in list(roles_created.items())[:5]:
        role = guild.get_role(int(role_id))
        if role and config:
            benefits_text += f"**{role.mention}**\n"
            benefits_text += f"• Cooldown: {config['cooldown']}h\n"
            benefits_text += f"• Cost: {config['cost'] if config['cost'] != 'default' else 'Default'}\n"
            benefits_text += f"• Daily Bonus: +{config['daily_bonus']} points\n\n"
    
    final_embed.add_field(
        name="🎭 Role Benefits",
        value=benefits_text[:1024],
        inline=False
    )
    
    await status_msg.edit(embed=final_embed)

@bot.command(name="configure_cookies")
@is_owner_or_admin()
async def configure_cookies(ctx):
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    if not server:
        await ctx.send("❌ Please run `!setup` first!")
        return
    
    embed = discord.Embed(
        title="🍪 Cookie Configuration",
        description="Current cookie settings:",
        color=0x5865f2
    )
    
    for cookie_type, config in server.get("cookies", {}).items():
        embed.add_field(
            name=f"{get_cookie_emoji(cookie_type)} {cookie_type.title()}",
            value=f"Cost: **{config['cost']}** pts\nCooldown: **{config['cooldown']}**h\nEnabled: {'✅' if config.get('enabled', True) else '❌'}",
            inline=True
        )
    
    embed.add_field(
        name="📝 Commands",
        value=(
            "`!setcookie <type> cost <amount>` - Set cost\n"
            "`!setcookie <type> cooldown <hours>` - Set cooldown\n"
            "`!setcookie <type> enabled true/false` - Enable/disable\n"
            "`!addcookie <type> <cost> <cooldown>` - Add new type"
        ),
        inline=False
    )
    
    await ctx.send(embed=embed)

def get_cookie_emoji(cookie_type: str) -> str:
    emojis = {
        "netflix": "🎬", "spotify": "🎵", "prime": "📦",
        "jiohotstar": "⭐", "tradingview": "📈", "chatgpt": "🤖",
        "claude": "🧠", "peacock": "🦚", "crunchyroll": "🍙",
        "canalplus": "📺"
    }
    return emojis.get(cookie_type, "🍪")

@bot.command(name="setcookie")
@is_owner_or_admin()
async def set_cookie(ctx, cookie_type: str, setting: str, value: str):
    valid_settings = ["cost", "cooldown", "directory", "enabled"]
    if setting not in valid_settings:
        await ctx.send(f"❌ Invalid setting! Use: {', '.join(valid_settings)}")
        return
    
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    if not server or cookie_type not in server.get("cookies", {}):
        await ctx.send("❌ Cookie type not found!")
        return
    
    if setting in ["cost", "cooldown"]:
        value = int(value)
    elif setting == "enabled":
        value = value.lower() == "true"
    
    await bot.db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$set": {f"cookies.{cookie_type}.{setting}": value}}
    )
    
    embed = discord.Embed(
        title="✅ Cookie Updated",
        description=f"Updated **{cookie_type}** {setting} to **{value}**",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command(name="addcookie")
@is_owner_or_admin()
async def add_cookie_type(ctx, cookie_type: str, cost: int, cooldown: int):
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    if not server:
        await ctx.send("❌ Please run `!setup` first!")
        return
    
    base_dir = f"D:/Discord Bot/cookies/{ctx.guild.id}/{cookie_type}"
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    
    cookie_data = {
        "cost": cost,
        "cooldown": cooldown,
        "directory": base_dir,
        "enabled": True,
        "base_cost": cost
    }
    
    await bot.db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$set": {f"cookies.{cookie_type}": cookie_data}}
    )
    
    embed = discord.Embed(
        title="✅ Cookie Type Added",
        description=f"Added new cookie type: **{cookie_type}**",
        color=0x00ff00
    )
    embed.add_field(name="💰 Cost", value=f"{cost} points", inline=True)
    embed.add_field(name="⏰ Cooldown", value=f"{cooldown} hours", inline=True)
    embed.add_field(name="📁 Directory", value=f"`{base_dir}`", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="setmod")
@is_owner_or_admin()
async def set_moderator(ctx, role: discord.Role):
    await bot.db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$addToSet": {"mod_roles": role.id}}
    )
    
    embed = discord.Embed(
        title="✅ Moderator Role Added",
        description=f"{role.mention} can now use moderation commands",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command(name="settings")
@is_owner_or_admin()
async def server_settings(ctx):
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    if not server:
        await ctx.send("❌ Server not configured!")
        return
    
    embed = discord.Embed(
        title="⚙️ Server Settings",
        description=f"Configuration for **{ctx.guild.name}**",
        color=0x5865f2
    )
    
    # Channels
    channels_text = ""
    for ch_type, ch_id in server.get("channels", {}).items():
        channel = bot.get_channel(ch_id)
        channels_text += f"**{ch_type}**: {channel.mention if channel else '❌ Deleted'}\n"
    embed.add_field(name="📺 Channels", value=channels_text or "None", inline=False)
    
    # Settings
    settings = server.get("settings", {})
    embed.add_field(
        name="⚙️ Configuration",
        value=(
            f"Feedback Required: {'✅' if settings.get('feedback_required', True) else '❌'}\n"
            f"Feedback Timeout: {settings.get('feedback_timeout', 15)} minutes\n"
            f"Max Daily Claims: {settings.get('max_daily_claims', 10)}\n"
            f"Warnings before Blacklist: {settings.get('blacklist_after_warnings', 3)}"
        ),
        inline=True
    )
    
    # Status
    embed.add_field(
        name="📊 Status",
        value=(
            f"Enabled: {'✅' if server.get('enabled', True) else '❌'}\n"
            f"Role-based: {'✅' if server.get('role_based', True) else '❌'}\n"
            f"Cookie Types: {len(server.get('cookies', {}))}\n"
            f"Configured Roles: {len(server.get('roles', {}))}"
        ),
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.command(name="toggle")
@is_owner_or_admin()
async def toggle_feature(ctx, feature: str):
    valid_features = ["feedback", "rolebased", "bot"]
    if feature not in valid_features:
        await ctx.send(f"❌ Invalid feature! Use: {', '.join(valid_features)}")
        return
    
    server = await bot.db.servers.find_one({"server_id": ctx.guild.id})
    if not server:
        await ctx.send("❌ Server not configured!")
        return
    
    if feature == "feedback":
        current = server.get("settings", {}).get("feedback_required", True)
        await bot.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$set": {"settings.feedback_required": not current}}
        )
        status = "disabled" if current else "enabled"
    elif feature == "rolebased":
        current = server.get("role_based", True)
        await bot.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$set": {"role_based": not current}}
        )
        status = "disabled" if current else "enabled"
    elif feature == "bot":
        current = server.get("enabled", True)
        await bot.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$set": {"enabled": not current}}
        )
        status = "disabled" if current else "enabled"
    
    embed = discord.Embed(
        title="✅ Feature Toggled",
        description=f"**{feature}** has been **{status}**",
        color=0x00ff00 if status == "enabled" else 0xff0000
    )
    await ctx.send(embed=embed)

async def initialize_bot_config():
    config_doc = {
        "_id": "bot_config",
        "owner_id": OWNER_ID,
        "main_server_id": MAIN_SERVER_ID,
        "main_server_invite": MAIN_SERVER_INVITE,
        "main_log_channel": None,
        "appeals_channel": None,
        "analytics_channel": None,
        "feedback_minutes": 15,
        "point_rates": {
            "daily": 2,
            "invite": 2,
            "boost": 50,
            "vote": 5
        },
        "blacklist_days": 30,
        "maintenance_mode": False,
        "default_cookies": {
            "netflix": {"cost": 5, "cooldown": 72, "directory": "", "enabled": True, "base_cost": 5},
            "spotify": {"cost": 3, "cooldown": 48, "directory": "", "enabled": True, "base_cost": 3},
            "prime": {"cost": 4, "cooldown": 72, "directory": "", "enabled": True, "base_cost": 4},
            "jiohotstar": {"cost": 3, "cooldown": 48, "directory": "", "enabled": True, "base_cost": 3},
            "tradingview": {"cost": 8, "cooldown": 96, "directory": "", "enabled": True, "base_cost": 8},
            "chatgpt": {"cost": 10, "cooldown": 96, "directory": "", "enabled": True, "base_cost": 10},
            "claude": {"cost": 12, "cooldown": 120, "directory": "", "enabled": True, "base_cost": 12},
            "peacock": {"cost": 4, "cooldown": 72, "directory": "", "enabled": True, "base_cost": 4},
            "crunchyroll": {"cost": 4, "cooldown": 48, "directory": "", "enabled": True, "base_cost": 4},
            "canalplus": {"cost": 6, "cooldown": 72, "directory": "", "enabled": True, "base_cost": 6}
        },
        "default_roles": {
            "free": {"name": "Free", "cooldown": 72, "cost": "default", "access": ["netflix", "spotify", "prime"]},
            "premium": {"name": "Premium", "cooldown": 24, "cost": 2, "access": ["all"]},
            "vip": {"name": "VIP", "cooldown": 12, "cost": 1, "access": ["all"]},
            "booster": {"name": "Booster", "cooldown": 0, "cost": 0, "access": ["all"]},
            "staff": {"name": "Staff", "cooldown": 0, "cost": 0, "access": ["all"]}
        }
    }
    
    await bot.db.config.update_one(
        {"_id": "bot_config"},
        {"$set": config_doc},
        upsert=True
    )

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="🍪 Cookie Bot Setup Help",
        description="Complete setup guide and commands",
        color=0x5865f2
    )
    
    embed.add_field(
        name="🚀 Quick Setup",
        value=(
            "`!setup` - Run the setup wizard\n"
            "`!setup_roles` - Configure role benefits\n"
            "`!configure_cookies` - Manage cookie types"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Configuration",
        value=(
            "`!setcookie <type> <setting> <value>` - Configure cookies\n"
            "`!addcookie <type> <cost> <cooldown>` - Add new cookie\n"
            "`!setmod <role>` - Add moderator role\n"
            "`!toggle <feature>` - Toggle features\n"
            "`!settings` - View current settings"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📚 Resources",
        value=(
            f"• [Support Server]({MAIN_SERVER_INVITE})\n"
            "• [Documentation](https://cookiebot.com/docs)\n"
            "• Contact: support@cookiebot.com"
        ),
        inline=False
    )
    
    await ctx.send(embed=embed)

bot.run(BOT_TOKEN)