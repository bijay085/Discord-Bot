# main.py

import discord
from discord.ext import commands
from discord import app_commands
import motor.motor_asyncio
import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from setup folder
load_dotenv('setup/.env')

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.remove_command('help')
        self.start_time = datetime.now(timezone.utc)
        
    async def setup_hook(self):
        await self.load_cogs()
        # Just sync without clearing
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} commands")
    
    async def load_cogs(self):
        cogs = [
            "cogs.cookie",
            "cogs.points",
            "cogs.admin",
            "cogs.invite",
            "cogs.directory",
            "cogs.analytics"  # Added analytics cog

        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"Loaded cog: {cog}")
            except Exception as e:
                print(f"Failed to load cog {cog}: {e}")

bot = MyBot()

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
BOT_TOKEN = os.getenv("BOT_TOKEN")

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = mongo_client[DATABASE_NAME]
bot.db = db

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    print(f"Connected to {len(bot.guilds)} servers")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if bot.user.mentioned_in(message) and message.content.replace(f'<@{bot.user.id}>', '').strip() == '':
        uptime = datetime.now(timezone.utc) - bot.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        embed = discord.Embed(
            title="🍪 Cookie Bot Status",
            description=f"Hey {message.author.mention}! I'm online and ready to serve cookies!",
            color=discord.Color.blue()
        )
        embed.add_field(name="⏰ Uptime", value=f"{days}d {hours}h {minutes}m {seconds}s", inline=True)
        embed.add_field(name="📊 Servers", value=f"{len(bot.guilds)}", inline=True)
        embed.add_field(name="🏓 Ping", value=f"{round(bot.latency * 1000)}ms", inline=True)
        embed.set_footer(text="Use /help for commands")
        
        await message.reply(embed=embed)
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}", ephemeral=True)
    else:
        print(f"Error: {error}")

@bot.tree.command(name="forcesync", description="Force sync all commands (Owner Only)")
async def forcesync(interaction: discord.Interaction):
    config = await db.config.find_one({"_id": "bot_config"})
    if interaction.user.id != config.get("owner_id"):
        await interaction.response.send_message("❌ This command is owner only!", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        commands = await bot.tree.sync()
        
        embed = discord.Embed(
            title="✅ Force Sync Complete",
            description=f"Synced {len(commands)} commands",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to sync: {e}", ephemeral=True)

@bot.tree.command(name="setup", description="Setup the bot for this server (Admin Only)")
@app_commands.default_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    await interaction.response.defer()
    
    guild = interaction.guild
    embed = discord.Embed(
        title="🔧 Server Setup",
        description="Setting up the bot...",
        color=discord.Color.blue()
    )
    
    existing_category = discord.utils.get(guild.categories, name="🍪 Cookie Bot")
    if existing_category:
        category = existing_category
    else:
        category = await guild.create_category("🍪 Cookie Bot")
    
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
            channel = await category.create_text_channel(channel_name, topic=topic)
        channels_created[ch_type] = channel.id
    
    config = await db.config.find_one({"_id": "bot_config"})
    default_cookies = config.get("default_cookies", {})
    
    roles_created = {}
    role_configs = [
        ("🍪 Free Cookie", discord.Color.default(), "free"),
        ("⭐ Premium Cookie", discord.Color.gold(), "premium"),
        ("💎 VIP Cookie", discord.Color.purple(), "vip")
    ]
    
    for role_name, color, role_type in role_configs:
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            role = await guild.create_role(name=role_name, color=color)
        
        default_role_config = config.get("default_roles", {}).get(role_type, {})
        if default_role_config:
            roles_created[str(role.id)] = default_role_config
    
    server_data = {
        "server_id": guild.id,
        "server_name": guild.name,
        "server_owner": guild.owner_id,
        "admins": [guild.owner_id],
        "channels": channels_created,
        "cookies": default_cookies,
        "role_based": True,
        "roles": roles_created,
        "enabled": True
    }
    
    await db.servers.update_one(
        {"server_id": guild.id},
        {"$set": server_data},
        upsert=True
    )
    
    embed = discord.Embed(
        title="✅ Setup Complete!",
        description=f"Channels: {len(channels_created)}\nRoles: {len(roles_created)}",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed)

if __name__ == "__main__":
    bot.run(BOT_TOKEN)