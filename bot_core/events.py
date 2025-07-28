import discord
from discord.ext import commands
from datetime import datetime, timezone
import platform
import psutil
import logging
from .views import BotControlView

logger = logging.getLogger('CookieBot')

class EventHandler:
    def __init__(self, bot):
        self.bot = bot
        
    async def on_ready(self):
        print(f"✅ Bot logged in as {self.bot.user} (ID: {self.bot.user.id})")
        print(f"🌐 Connected to {len(self.bot.guilds)} servers with {sum(g.member_count for g in self.bot.guilds):,} total users")
        
        try:
            synced = await self.bot.tree.sync()
            print(f"🔄 Synced {len(synced)} slash commands globally")
            
            all_commands = list(self.bot.tree.get_commands())
            guild_commands = list(self.bot.tree.get_commands(guild=None))
            
            print(f"📋 Total commands available: {len(all_commands)}")
            
            for guild in self.bot.guilds[:5]:
                print(f"  ✓ Connected to {guild.name} ({guild.member_count} members)")
                    
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")
            print(f"❌ Failed to sync commands: {e}")
        
        config = await self.bot.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.bot.get_channel(config["main_log_channel"])
            if channel:
                embed = discord.Embed(
                    title="🟢 Bot Online",
                    description=f"Cookie Bot is now operational and ready to serve!",
                    color=0x2ECC71,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="🖥️ Servers", value=f"**{len(self.bot.guilds)}**", inline=True)
                embed.add_field(name="👥 Users", value=f"**{sum(g.member_count for g in self.bot.guilds):,}**", inline=True)
                embed.add_field(name="📡 Latency", value=f"**{round(self.bot.latency * 1000)}ms**", inline=True)
                embed.add_field(name="🐍 Python", value=f"**{platform.python_version()}**", inline=True)
                embed.add_field(name="📚 Discord.py", value=f"**{discord.__version__}**", inline=True)
                embed.add_field(name="💾 RAM", value=f"**{psutil.virtual_memory().percent}%**", inline=True)
                embed.set_thumbnail(url=self.bot.user.avatar.url)
                embed.set_footer(text="Cookie Bot Premium v2.0", icon_url=self.bot.user.avatar.url)
                
                view = BotControlView(self.bot)
                message = await channel.send(embed=view.create_status_embed(), view=view)
                self.bot.status_messages[channel.id] = message.id
    
    async def on_guild_join(self, guild):
        print(f"🎉 Joined new server: {guild.name} (ID: {guild.id}) with {guild.member_count} members")
        
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
        
        embed.set_thumbnail(url=self.bot.user.avatar.url)
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
            print(f"⚠️ Could not send welcome message to {guild.name}")
        
        await self.bot.db.servers.insert_one({
            "server_id": guild.id,
            "server_name": guild.name,
            "joined_at": datetime.now(timezone.utc),
            "member_count": guild.member_count,
            "owner_id": guild.owner_id,
            "enabled": False,
            "setup_complete": False
        })
        
        config = await self.bot.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.bot.get_channel(config["main_log_channel"])
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
                log_embed.add_field(name="📊 Total Servers", value=f"**{len(self.bot.guilds)}**", inline=True)
                
                if guild.icon:
                    log_embed.set_thumbnail(url=guild.icon.url)
                
                if guild.banner:
                    log_embed.set_image(url=guild.banner.url)
                    
                await channel.send(embed=log_embed)
    
    async def on_guild_remove(self, guild):
        print(f"👋 Removed from server: {guild.name} (ID: {guild.id})")
        
        await self.bot.db.servers.update_one(
            {"server_id": guild.id},
            {
                "$set": {
                    "left_at": datetime.now(timezone.utc),
                    "active": False
                }
            }
        )
        
        config = await self.bot.db.config.find_one({"_id": "bot_config"})
        if config and config.get("main_log_channel"):
            channel = self.bot.get_channel(config["main_log_channel"])
            if channel:
                log_embed = discord.Embed(
                    title="📤 Server Left",
                    color=0xE74C3C,
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.add_field(name="🏷️ Server", value=guild.name, inline=True)
                log_embed.add_field(name="🆔 ID", value=f"`{guild.id}`", inline=True)
                log_embed.add_field(name="👥 Members", value=f"**{guild.member_count:,}**", inline=True)
                log_embed.add_field(name="📊 Total Servers", value=f"**{len(self.bot.guilds)}**", inline=True)
                log_embed.add_field(name="💔 Total Users Lost", value=f"**{guild.member_count:,}**", inline=True)
                
                server_data = await self.bot.db.servers.find_one({"server_id": guild.id})
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
        
        self.bot.command_stats[command_name] = self.bot.command_stats.get(command_name, 0) + 1
        
        await self.bot.db.analytics.insert_one({
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
            
            config = await self.bot.db.config.find_one({"_id": "bot_config"})
            if config and config.get("error_webhook"):
                webhook = self.bot.error_webhooks.get("global")
                if not webhook:
                    webhook = discord.Webhook.from_url(
                        config["error_webhook"],
                        session=self.bot.session
                    )
                    self.bot.error_webhooks["global"] = webhook
                
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