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
            "cogs.directory",
            "cogs.economy",
            "cogs.events",
            "cogs.premium",
            "cogs.analytics"
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
        bot.logger.info(f"✅ Synced {len(synced)} slash commands")
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

async def main():
    async with bot:
        await bot.start(os.getenv("BOT_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())