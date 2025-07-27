import discord
from discord.ext import commands
import motor.motor_asyncio
import os
import asyncio
from dotenv import load_dotenv
import aiohttp
import logging
from datetime import datetime, timezone

load_dotenv("setup/.env")

class CookieBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🍪 /help | Cookie Store"
            ),
            status=discord.Status.online,
            help_command=None
        )
        self.session = None
        self.start_time = datetime.now(timezone.utc)
        self.logger = self.setup_logging()
       
    def setup_logging(self):
        logger = logging.getLogger('CookieBot')
        logger.setLevel(logging.INFO)
       
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
       
        return logger
       
    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.load_extensions()
       
    async def load_extensions(self):
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
                self.logger.info(f"✅ Loaded: {cog}")
            except Exception as e:
                self.logger.error(f"❌ Failed to load {cog}: {e}")
               
    async def close(self):
        await super().close()
        if self.session:
            await self.session.close()

bot = CookieBot()
bot.db = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URI"))[os.getenv("DATABASE_NAME", "discord_bot")]

@bot.event
async def on_ready():
    bot.logger.info(f"🍪 {bot.user} is online!")
    bot.logger.info(f"📊 Connected to {len(bot.guilds)} servers")
    bot.logger.info(f"👥 Serving {sum(g.member_count for g in bot.guilds)} users")
   
    try:
        synced = await bot.tree.sync()
        bot.logger.info(f"✅ Synced {len(synced)} slash commands globally")
        
        for guild in bot.guilds:
            try:
                guild_synced = await bot.tree.sync(guild=guild)
                bot.logger.info(f"✅ Synced {len(guild_synced)} commands in {guild.name}")
            except Exception as e:
                bot.logger.error(f"❌ Failed to sync in {guild.name}: {e}")
                
    except Exception as e:
        bot.logger.error(f"❌ Failed to sync commands: {e}")
   
    config = await bot.db.config.find_one({"_id": "bot_config"})
    if config and config.get("main_log_channel"):
        channel = bot.get_channel(config["main_log_channel"])
        if channel:
            embed = discord.Embed(
                title="🟢 Bot Online",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Servers", value=f"```{len(bot.guilds)}```", inline=True)
            embed.add_field(name="Users", value=f"```{sum(g.member_count for g in bot.guilds)}```", inline=True)
            embed.add_field(name="Latency", value=f"```{round(bot.latency * 1000)}ms```", inline=True)
            embed.set_thumbnail(url=bot.user.display_avatar.url)
            await channel.send(embed=embed)

@bot.event
async def on_guild_join(guild):
    bot.logger.info(f"📥 Joined: {guild.name} ({guild.id})")
   
    try:
        await bot.tree.sync(guild=guild)
        bot.logger.info(f"✅ Synced commands for new guild: {guild.name}")
    except Exception as e:
        bot.logger.error(f"❌ Failed to sync for new guild {guild.name}: {e}")
   
    embed = discord.Embed(
        title="🍪 Cookie Bot Setup",
        description="Thank you for adding Cookie Bot!",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="🚀 Quick Start",
        value="```\n/setup - Complete server setup\n/help - View all commands\n/guide - Setup guide```",
        inline=False
    )
    embed.add_field(
        name="📚 Features",
        value="• Cookie claiming system\n• Points economy\n• Role-based benefits\n• Invite tracking\n• Analytics dashboard",
        inline=False
    )
    embed.add_field(
        name="🔗 Links",
        value=f"[Support Server]({os.getenv('MAIN_SERVER_INVITE')}) • [Documentation](https://cookiebot.com/docs)",
        inline=False
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Cookie Bot v2.0 • {guild.member_count} members")
   
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)
            break
           
    config = await bot.db.config.find_one({"_id": "bot_config"})
    if config and config.get("main_log_channel"):
        log_channel = bot.get_channel(config["main_log_channel"])
        if log_channel:
            log_embed = discord.Embed(
                title="📥 New Server Joined",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.add_field(name="Server", value=guild.name, inline=True)
            log_embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
            log_embed.add_field(name="Members", value=guild.member_count, inline=True)
            log_embed.add_field(name="Owner", value=f"{guild.owner} ({guild.owner.id})", inline=False)
            if guild.icon:
                log_embed.set_thumbnail(url=guild.icon.url)
            await log_channel.send(embed=log_embed)

@bot.event
async def on_guild_remove(guild):
    bot.logger.info(f"📤 Left: {guild.name} ({guild.id})")
   
    config = await bot.db.config.find_one({"_id": "bot_config"})
    if config and config.get("main_log_channel"):
        log_channel = bot.get_channel(config["main_log_channel"])
        if log_channel:
            embed = discord.Embed(
                title="📤 Server Left",
                color=0xff0000,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Server", value=guild.name, inline=True)
            embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
            embed.add_field(name="Members", value=guild.member_count, inline=True)
            await log_channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Argument",
            description=f"Missing required argument: `{error.param.name}`",
            color=0xff0000
        )
        await ctx.send(embed=embed, ephemeral=True)
    elif isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏰ Cooldown Active",
            description=f"Try again in **{error.retry_after:.1f}** seconds",
            color=0xffa500
        )
        await ctx.send(embed=embed, ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="🚫 Missing Permissions",
            description="You don't have permission to use this command",
            color=0xff0000
        )
        await ctx.send(embed=embed, ephemeral=True)
    else:
        bot.logger.error(f"Unhandled error: {error}")
        embed = discord.Embed(
            title="❌ Error Occurred",
            description="An unexpected error occurred. Please try again later.",
            color=0xff0000
        )
        await ctx.send(embed=embed, ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏰ Cooldown Active",
            description=f"Try again in **{error.retry_after:.1f}** seconds",
            color=0xffa500
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        bot.logger.error(f"App command error: {error}")

@bot.command()
@commands.is_owner()
async def sync(ctx):
    """Force sync all commands"""
    await ctx.defer()
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Force synced {len(synced)} global commands")
        
        for guild in bot.guilds:
            try:
                guild_synced = await bot.tree.sync(guild=guild)
                await ctx.send(f"✅ Synced {len(guild_synced)} commands in {guild.name}")
            except Exception as e:
                await ctx.send(f"❌ Failed to sync in {guild.name}: {e}")
    except Exception as e:
        await ctx.send(f"❌ Sync failed: {e}")

@bot.hybrid_command(name="ping", description="Check bot latency")
async def ping(ctx):
    """Test command to verify bot is working"""
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: **{round(bot.latency * 1000)}ms**",
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def listcmds(ctx):
    """List all registered commands"""
    commands_list = []
    for command in bot.tree.get_commands():
        commands_list.append(f"/{command.name} - {command.description}")
    
    if commands_list:
        embed = discord.Embed(
            title="📋 Registered Commands",
            description="\n".join(commands_list[:20]),
            color=0x00ff00
        )
        if len(commands_list) > 20:
            embed.set_footer(text=f"Showing 20 of {len(commands_list)} commands")
    else:
        embed = discord.Embed(
            title="❌ No Commands Found",
            description="No slash commands are registered",
            color=0xff0000
        )
    
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def forcesync(ctx):
    """Force sync commands to specific guild"""
    await ctx.defer()
    
    try:
        # Clear existing commands
        bot.tree.clear_commands(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
        
        # Copy global commands to guild
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        
        await ctx.send(f"✅ Force synced {len(synced)} commands to this guild")
    except Exception as e:
        await ctx.send(f"❌ Force sync failed: {e}")

@bot.command()
@commands.is_owner()
async def clearcmds(ctx):
    """Clear all commands and resync"""
    await ctx.defer()
    
    try:
        # Clear all commands
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        
        await ctx.send("✅ Cleared all global commands. Restart bot to re-register.")
    except Exception as e:
        await ctx.send(f"❌ Clear failed: {e}")

async def main():
    async with bot:
        await bot.start(os.getenv("BOT_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())