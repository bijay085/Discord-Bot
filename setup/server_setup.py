import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "1192694890530869369"))
MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "1348916338961154088"))
MAIN_SERVER_INVITE = os.getenv("MAIN_SERVER_INVITE", "https://discord.gg/WVq522fsr3")

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = mongo_client[DATABASE_NAME]

def is_owner_or_admin():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        server = await db.servers.find_one({"server_id": ctx.guild.id})
        if server and ctx.author.id in server.get("admins", []):
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        return False
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    print(f"Connected to {len(bot.guilds)} servers")
    
    # Get main log channel from config
    config = await db.config.find_one({"_id": "bot_config"})
    if config and config.get("main_log_channel"):
        main_channel = bot.get_channel(config["main_log_channel"])
        if main_channel:
            embed = discord.Embed(
                title="🟢 Bot Online",
                description=f"Connected to {len(bot.guilds)} servers",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await main_channel.send(embed=embed)

@bot.event
async def on_guild_join(guild):
    print(f"Joined new server: {guild.name} ({guild.id})")
    
    embed = discord.Embed(
        title="Thanks for adding me! 🍪",
        description=(
            "To set up the bot, an administrator needs to run:\n"
            "`!setup` - Complete server setup\n"
            "`!help` - View all commands"
        ),
        color=discord.Color.green()
    )
    
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)
            break

@bot.command(name="setup")
@is_owner_or_admin()
async def setup_server(ctx):
    guild = ctx.guild
    
    embed = discord.Embed(
        title="🔧 Server Setup",
        description="I will now set up everything for this server!",
        color=discord.Color.blue()
    )
    status_msg = await ctx.send(embed=embed)
    
    existing_category = discord.utils.get(guild.categories, name="🍪 Cookie Bot")
    if existing_category:
        embed.add_field(name="⚠️ Warning", value="Setup already exists! Updating configuration...", inline=False)
        await status_msg.edit(embed=embed)
        category = existing_category
    else:
        category = await guild.create_category(
            "🍪 Cookie Bot",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(send_messages=False),
                guild.me: discord.PermissionOverwrite(
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                )
            }
        )
        embed.add_field(name="✅ Category", value="Created category!", inline=False)
        await status_msg.edit(embed=embed)
    
    channels_created = {}
    
    channel_configs = [
        ("🍪cookie-claims", "Use bot commands here", "cookie"),
        ("📸feedback-photos", "Submit feedback screenshots", "feedback"),
        ("📝bot-logs", "Bot activity logs", "log"),
        ("📢announcements", "Bot announcements", "announcement")
    ]
    
    for channel_name, topic, ch_type in channel_configs:
        channel = discord.utils.get(category.channels, name=channel_name)
        if not channel:
            channel = await category.create_text_channel(
                channel_name,
                topic=topic
            )
            embed.add_field(name=f"✅ {ch_type.title()}", value=f"Created {channel.mention}", inline=True)
        else:
            embed.add_field(name=f"✅ {ch_type.title()}", value=f"Using {channel.mention}", inline=True)
        
        channels_created[ch_type] = channel.id
    
    await status_msg.edit(embed=embed)
    
    config = await db.config.find_one({"_id": "bot_config"})
    default_cookies = config.get("default_cookies", {})
    
    roles_created = {}
    role_configs = [
        ("🍪 Free Cookie", discord.Color.default(), "free"),
        ("⭐ Premium Cookie", discord.Color.gold(), "premium"),
        ("💎 VIP Cookie", discord.Color.purple(), "vip"),
        ("🎯 Inviter Cookie", discord.Color.blue(), "inviter"),
        ("🛡️ Staff Cookie", discord.Color.red(), "staff"),
        ("🚫 Cookie Blacklist", discord.Color.dark_red(), "blacklist")
    ]
    
    for role_name, color, role_type in role_configs:
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            role = await guild.create_role(
                name=role_name,
                color=color,
                mentionable=False
            )
            embed.add_field(name=f"✅ Role", value=f"Created {role.mention}", inline=True)
        else:
            embed.add_field(name=f"✅ Role", value=f"Using {role.mention}", inline=True)
        
        if role_type != "blacklist":
            default_role_config = config.get("default_roles", {}).get(role_type, {})
            if default_role_config:
                roles_created[str(role.id)] = {
                    "name": default_role_config.get("name", role_type),
                    "cooldown": default_role_config.get("cooldown", 72),
                    "cost": default_role_config.get("cost", "default"),
                    "access": default_role_config.get("access", ["all"])
                }
    
    booster_role = guild.premium_subscriber_role
    if booster_role:
        booster_config = config.get("default_roles", {}).get("booster", {})
        roles_created[str(booster_role.id)] = {
            "name": "Booster",
            "cooldown": booster_config.get("cooldown", 6),
            "cost": booster_config.get("cost", 0),
            "access": booster_config.get("access", ["all"])
        }
        embed.add_field(name=f"✅ Booster", value=f"Detected {booster_role.mention}", inline=True)
    
    await status_msg.edit(embed=embed)
    
    server_data = {
        "server_id": guild.id,
        "server_name": guild.name,
        "invite_link": None,
        "server_owner": guild.owner_id,
        "admins": [guild.owner_id],
        "channels": channels_created,
        "cookies": default_cookies,
        "role_based": True,
        "roles": roles_created,
        "whitelist_mode": False,
        "whitelisted_servers": [],
        "enabled": True
    }
    
    await db.servers.update_one(
        {"server_id": guild.id},
        {"$set": server_data},
        upsert=True
    )
    
    final_embed = discord.Embed(
        title="✅ Setup Complete!",
        description="Your server is now fully configured!",
        color=discord.Color.green()
    )
    final_embed.add_field(name="Channels", value=f"{len(channels_created)} configured", inline=True)
    final_embed.add_field(name="Roles", value=f"{len(roles_created)} configured", inline=True)
    final_embed.add_field(name="Cookies", value=f"{len(default_cookies)} types available", inline=True)
    
    await status_msg.edit(embed=final_embed)
    
    cookie_channel = bot.get_channel(channels_created.get("cookie"))
    if cookie_channel:
        welcome_embed = discord.Embed(
            title="🍪 Cookie Bot Ready!",
            description=(
                "**Available Commands:**\n"
                "`/cookie <type>` - Get a cookie (costs points)\n"
                "`/daily` - Claim 2 daily points\n"
                "`/points` - Check your points\n"
                "`/help` - See all commands\n\n"
                "**Available Cookies:**\n"
                "• Netflix (5 pts) • Spotify (3 pts) • Prime (4 pts)\n"
                "• JioHotstar (3 pts) • TradingView (8 pts) • ChatGPT (10 pts)\n"
                "• Claude (12 pts) • Peacock (4 pts) • Crunchyroll (4 pts)\n"
                "• CanalPlus (6 pts)\n\n"
                "⚠️ **Important:** Submit feedback within 15 minutes!"
            ),
            color=discord.Color.green()
        )
        await cookie_channel.send(embed=welcome_embed)
    
    log_channel = bot.get_channel(channels_created.get("log"))
    if log_channel:
        log_embed = discord.Embed(
            title="✅ Server Setup Complete",
            description=f"Setup completed by {ctx.author.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Server", value=guild.name, inline=True)
        log_embed.add_field(name="Channels", value=f"{len(channels_created)} created", inline=True)
        log_embed.add_field(name="Roles", value=f"{len(roles_created)} configured", inline=True)
        await log_channel.send(embed=log_embed)
    
    # Also log to main server if different
    if guild.id != MAIN_SERVER_ID:
        config = await db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            main_log = bot.get_channel(config["main_log_channel"])
            if main_log:
                main_embed = discord.Embed(
                    title="🔧 New Server Setup",
                    description=f"Setup completed in **{guild.name}**",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                main_embed.add_field(name="Server ID", value=guild.id, inline=True)
                main_embed.add_field(name="Members", value=guild.member_count, inline=True)
                main_embed.add_field(name="Setup By", value=ctx.author.mention, inline=True)
                await main_log.send(embed=main_embed)

@bot.command(name="addadmin")
@is_owner_or_admin()
async def add_admin(ctx, member: discord.Member):
    await db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$addToSet": {"admins": member.id}}
    )
    
    embed = discord.Embed(
        title="✅ Admin Added",
        description=f"{member.mention} is now a bot admin!",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="setchannel")
@is_owner_or_admin()
async def set_channel(ctx, channel_type: str, channel: discord.TextChannel):
    valid_types = ["cookie", "feedback", "log", "announcement"]
    if channel_type not in valid_types:
        await ctx.send(f"Invalid type! Use: {', '.join(valid_types)}")
        return
    
    await db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$set": {f"channels.{channel_type}": channel.id}}
    )
    
    embed = discord.Embed(
        title="✅ Channel Updated",
        description=f"{channel_type.capitalize()} channel set to {channel.mention}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="setcookie")
@is_owner_or_admin()
async def set_cookie(ctx, cookie_type: str, setting: str, value: str):
    valid_settings = ["cost", "cooldown", "directory", "enabled"]
    if setting not in valid_settings:
        await ctx.send(f"Invalid setting! Use: {', '.join(valid_settings)}")
        return
    
    if setting in ["cost", "cooldown"]:
        value = int(value)
    elif setting == "enabled":
        value = value.lower() == "true"
    
    await db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$set": {f"cookies.{cookie_type}.{setting}": value}}
    )
    
    embed = discord.Embed(
        title="✅ Cookie Settings Updated",
        description=f"{cookie_type} {setting} set to: {value}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="addcookie")
@is_owner_or_admin()
async def add_cookie_type(ctx, cookie_type: str, cost: int, cooldown: int, directory: str):
    cookie_data = {
        "cost": cost,
        "cooldown": cooldown,
        "directory": directory,
        "enabled": True
    }
    
    await db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$set": {f"cookies.{cookie_type}": cookie_data}}
    )
    
    embed = discord.Embed(
        title="✅ Cookie Type Added",
        description=f"Added {cookie_type} cookie!",
        color=discord.Color.green()
    )
    embed.add_field(name="Cost", value=f"{cost} points", inline=True)
    embed.add_field(name="Cooldown", value=f"{cooldown} hours", inline=True)
    embed.add_field(name="Directory", value=directory, inline=False)
    await ctx.send(embed=embed)

@bot.command(name="setrole")
@is_owner_or_admin()
async def set_role(ctx, role: discord.Role, cooldown: int, cost: int, access: str):
    access_list = ["all"] if access.lower() == "all" else access.split(",")
    
    role_data = {
        "name": role.name,
        "cooldown": cooldown,
        "cost": cost,
        "access": access_list
    }
    
    await db.servers.update_one(
        {"server_id": ctx.guild.id},
        {"$set": {f"roles.{role.id}": role_data}}
    )
    
    embed = discord.Embed(
        title="✅ Role Configuration Updated",
        description=f"Updated settings for {role.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="Cooldown", value=f"{cooldown} hours", inline=True)
    embed.add_field(name="Cost", value=f"{cost} points", inline=True)
    embed.add_field(name="Access", value=", ".join(access_list), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="serverinfo")
@is_owner_or_admin()
async def server_info(ctx):
    server = await db.servers.find_one({"server_id": ctx.guild.id})
    
    if not server:
        await ctx.send("Server not found in database! Run `!setup` first.")
        return
    
    embed = discord.Embed(
        title=f"Server Configuration: {ctx.guild.name}",
        color=discord.Color.blue()
    )
    
    channels = server.get("channels", {})
    channel_info = []
    for ch_type, ch_id in channels.items():
        if ch_id:
            channel = bot.get_channel(ch_id)
            if channel:
                channel_info.append(f"{ch_type}: {channel.mention}")
            else:
                channel_info.append(f"{ch_type}: ❌ Deleted")
    embed.add_field(name="Channels", value="\n".join(channel_info) or "None set", inline=False)
    
    cookies = server.get("cookies", {})
    cookie_info = []
    for cookie_type, config in cookies.items():
        if config.get("enabled", True):
            cookie_info.append(f"{cookie_type}: {config['cost']} pts, {config['cooldown']}h")
    embed.add_field(name="Cookies", value="\n".join(cookie_info[:5]) or "None", inline=False)
    
    embed.add_field(name="Role-based", value="✅" if server.get("role_based") else "❌", inline=True)
    embed.add_field(name="Enabled", value="✅" if server.get("enabled") else "❌", inline=True)
    embed.add_field(name="Total Cookies", value=len(cookies), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="quicksetup")
@commands.is_owner()
async def quick_setup_all(ctx):
    config = await db.config.find_one({"_id": "bot_config"})
    default_cookies = config.get("default_cookies", {})
    
    success = 0
    failed = 0
    
    for guild in bot.guilds:
        try:
            existing = await db.servers.find_one({"server_id": guild.id})
            if not existing:
                server_data = {
                    "server_id": guild.id,
                    "server_name": guild.name,
                    "invite_link": None,
                    "server_owner": guild.owner_id,
                    "admins": [guild.owner_id],
                    "channels": {
                        "cookie": None,
                        "feedback": None,
                        "log": None,
                        "announcement": None
                    },
                    "cookies": default_cookies,
                    "role_based": True,
                    "roles": {},
                    "whitelist_mode": False,
                    "whitelisted_servers": [],
                    "enabled": True
                }
                await db.servers.insert_one(server_data)
                success += 1
        except Exception as e:
            print(f"Failed for {guild.name}: {e}")
            failed += 1
    
    await ctx.send(f"Quick setup complete! Success: {success}, Failed: {failed}")

bot.run(BOT_TOKEN)