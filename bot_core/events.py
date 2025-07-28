import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import platform
import psutil
import logging
import asyncio
import os
from .views import BotControlView

logger = logging.getLogger('CookieBot')

class EventHandler:
    def __init__(self, bot):
        self.bot = bot
        
    async def on_ready(self):
        print(f"✅ Logged in as {self.bot.user} (ID: {self.bot.user.id})")
        print(f"📊 {len(self.bot.guilds)} servers | {sum(g.member_count for g in self.bot.guilds):,} users")
        
        try:
            synced = await self.bot.tree.sync()
            print(f"🔄 Synced {len(synced)} commands")
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")
            print(f"❌ Failed to sync commands")
        
        # Send announcement to announcement channels from database
        await asyncio.sleep(2)  # Small delay to ensure everything is loaded
        
        # Get all servers with announcement channels configured
        servers_with_announcement = await self.bot.db.servers.find({
            "channels.announcement": {"$exists": True, "$ne": None},
            "enabled": True
        }).to_list(None)
        
        if servers_with_announcement:
            # Get comprehensive statistics
            total_users = await self.bot.db.users.count_documents({})
            total_cookies_claimed = await self.bot.db.statistics.find_one({"_id": "global_stats"})
            active_users_today = await self.bot.db.users.count_documents({
                "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=1)}
            })
            active_users_week = await self.bot.db.users.count_documents({
                "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)}
            })
            
            # Get cookie stock information
            stock_info = {}
            total_stock = 0
            config = await self.bot.db.config.find_one({"_id": "bot_config"})
            if config and config.get("default_cookies"):
                for cookie_type, cookie_config in config["default_cookies"].items():
                    directory = cookie_config.get("directory")
                    if directory and os.path.exists(directory):
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        count = len(files)
                        stock_info[cookie_type] = count
                        total_stock += count
            
            # Get top cookies
            top_cookies = []
            if total_cookies_claimed and total_cookies_claimed.get("total_claims"):
                sorted_cookies = sorted(total_cookies_claimed["total_claims"].items(), 
                                      key=lambda x: x[1], reverse=True)[:5]
                top_cookies = [(name.title(), count) for name, count in sorted_cookies]
            
            # Get recent activity
            recent_claims = await self.bot.db.users.count_documents({
                "last_claim.date": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)}
            })
            
            # Get blacklist stats
            blacklisted_users = await self.bot.db.users.count_documents({"blacklisted": True})
            
            # Send to each server's announcement channel
            for server_data in servers_with_announcement:
                announcement_channel_id = server_data["channels"]["announcement"]
                announcement_channel = self.bot.get_channel(announcement_channel_id)
                
                if announcement_channel:
                    try:
                        announcement_embed = discord.Embed(
                            title="🟢 Cookie Bot System Status",
                            description="```diff\n+ SYSTEM ONLINE\n+ ALL SERVICES OPERATIONAL\n```",
                            color=0x00ff00,
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        # Server & User Statistics
                        announcement_embed.add_field(
                            name="📊 Network Statistics",
                            value=f"```yaml\n"
                                  f"Servers      : {len(self.bot.guilds):,}\n"
                                  f"Total Users  : {sum(g.member_count for g in self.bot.guilds):,}\n"
                                  f"Registered   : {total_users:,}\n"
                                  f"Active (24h) : {active_users_today:,}\n"
                                  f"Active (7d)  : {active_users_week:,}\n"
                                  f"Blacklisted  : {blacklisted_users:,}\n"
                                  f"```",
                            inline=True
                        )
                        
                        # Cookie Statistics
                        announcement_embed.add_field(
                            name="🍪 Cookie Analytics",
                            value=f"```yaml\n"
                                  f"Total Claims : {total_cookies_claimed.get('all_time_claims', 0) if total_cookies_claimed else 0:,}\n"
                                  f"Claims (24h) : {recent_claims:,}\n"
                                  f"Total Stock  : {total_stock:,} files\n"
                                  f"Cookie Types : {len(stock_info)}\n"
                                  f"Avg Claims   : {(total_cookies_claimed.get('all_time_claims', 0) // max(total_users, 1)) if total_cookies_claimed else 0}/user\n"
                                  f"```",
                            inline=True
                        )
                        
                        # Stock Overview
                        stock_text = "```diff\n"
                        for cookie, count in sorted(stock_info.items(), key=lambda x: x[1], reverse=True)[:8]:
                            if count > 20:
                                stock_text += f"+ {cookie.ljust(12)}: {count:>3} ✓\n"
                            elif count > 10:
                                stock_text += f"! {cookie.ljust(12)}: {count:>3} ⚠\n"
                            elif count > 0:
                                stock_text += f"- {cookie.ljust(12)}: {count:>3} ⚠\n"
                            else:
                                stock_text += f"- {cookie.ljust(12)}: OUT ✗\n"
                        stock_text += "```"
                        
                        announcement_embed.add_field(
                            name="📦 Cookie Stock Levels",
                            value=stock_text,
                            inline=False
                        )
                        
                        # Top Cookies
                        if top_cookies:
                            top_text = "```yaml\n"
                            for i, (name, count) in enumerate(top_cookies, 1):
                                top_text += f"{i}. {name.ljust(12)}: {count:,} claims\n"
                            top_text += "```"
                            
                            announcement_embed.add_field(
                                name="🏆 Most Popular Cookies",
                                value=top_text,
                                inline=True
                            )
                        
                        # System Performance
                        announcement_embed.add_field(
                            name="💻 System Performance",
                            value=f"```yaml\n"
                                  f"Latency  : {round(self.bot.latency * 1000)}ms\n"
                                  f"RAM      : {psutil.virtual_memory().percent}%\n"
                                  f"CPU      : {psutil.cpu_percent()}%\n"
                                  f"Uptime   : {self.bot.get_uptime()}\n"
                                  f"Commands : {len(self.bot.commands)}\n"
                                  f"```",
                            inline=True
                        )
                        
                        announcement_embed.set_thumbnail(url=self.bot.user.avatar.url)
                        announcement_embed.set_footer(text="Cookie Bot v2.0 | Premium Edition | Auto-refresh available")
                        
                        # Create view with refresh button for announcement
                        view = AnnouncementRefreshView(self.bot)
                        
                        sent_message = await announcement_channel.send(embed=announcement_embed, view=view)
                        view.message = sent_message
                    except discord.Forbidden:
                        print(f"❌ No permission to send in {server_data.get('server_name', 'Unknown')} announcement channel")
                    except Exception as e:
                        print(f"❌ Failed to send announcement to {server_data.get('server_name', 'Unknown')}: {e}")
                else:
                    print(f"❌ Announcement channel {announcement_channel_id} not found for {server_data.get('server_name', 'Unknown')}")
        
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
        print(f"➕ Joined: {guild.name} ({guild.member_count} members)")
        
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
        print(f"➖ Left: {guild.name}")
        
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

class AnnouncementRefreshView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No timeout
        self.bot = bot
        self.message = None
        self.cooldowns = {}
        self.spam_violations = {}
        
    @discord.ui.button(label="Refresh Stats", style=discord.ButtonStyle.primary, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        now = datetime.now(timezone.utc)
        
        # Check if user has a penalty
        if user_id in self.spam_violations:
            penalty_end = self.spam_violations[user_id]
            if now < penalty_end:
                remaining_minutes = (penalty_end - now).total_seconds() / 60
                await interaction.response.send_message(
                    f"🚫 You have been temporarily restricted for spamming!\n"
                    f"⏰ Try again in **{remaining_minutes:.1f}** minutes.",
                    ephemeral=True
                )
                return
            else:
                del self.spam_violations[user_id]
        
        # Check cooldown
        if user_id in self.cooldowns:
            last_refresh, violation_count = self.cooldowns[user_id]
            time_passed = (now - last_refresh).total_seconds()
            
            if time_passed < 120:  # 2 minute cooldown
                remaining = 120 - time_passed
                new_violation_count = violation_count + 1
                self.cooldowns[user_id] = (last_refresh, new_violation_count)
                
                if new_violation_count >= 3:
                    penalty_end = now + timedelta(minutes=20)
                    self.spam_violations[user_id] = penalty_end
                    if user_id in self.cooldowns:
                        del self.cooldowns[user_id]
                    
                    await interaction.response.send_message(
                        f"🚫 **SPAM DETECTED!**\n"
                        f"You have been restricted for **20 minutes** for spamming.\n",
                        ephemeral=True
                    )
                    return
                else:
                    minutes = int(remaining // 60)
                    seconds = int(remaining % 60)
                    await interaction.response.send_message(
                        f"⏰ Please wait **{minutes}m {seconds}s** before refreshing!\n"
                        f"⚠️ Warning: {3 - new_violation_count} more attempts = 20min restriction.",
                        ephemeral=True
                    )
                    return
        
        # Update cooldown
        self.cooldowns[user_id] = (now, 0)
        
        # Defer response
        await interaction.response.defer()
        
        # Get updated statistics
        total_users = await self.bot.db.users.count_documents({})
        total_cookies_claimed = await self.bot.db.statistics.find_one({"_id": "global_stats"})
        active_users_today = await self.bot.db.users.count_documents({
            "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=1)}
        })
        active_users_week = await self.bot.db.users.count_documents({
            "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)}
        })
        
        # Get cookie stock information
        stock_info = {}
        total_stock = 0
        config = await self.bot.db.config.find_one({"_id": "bot_config"})
        if config and config.get("default_cookies"):
            for cookie_type, cookie_config in config["default_cookies"].items():
                directory = cookie_config.get("directory")
                if directory and os.path.exists(directory):
                    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                    count = len(files)
                    stock_info[cookie_type] = count
                    total_stock += count
        
        # Get top cookies
        top_cookies = []
        if total_cookies_claimed and total_cookies_claimed.get("total_claims"):
            sorted_cookies = sorted(total_cookies_claimed["total_claims"].items(), 
                                  key=lambda x: x[1], reverse=True)[:5]
            top_cookies = [(name.title(), count) for name, count in sorted_cookies]
        
        # Get recent activity
        recent_claims = await self.bot.db.users.count_documents({
            "last_claim.date": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)}
        })
        
        # Get blacklist stats
        blacklisted_users = await self.bot.db.users.count_documents({"blacklisted": True})
        
        # Create new embed
        announcement_embed = discord.Embed(
            title="🟢 Cookie Bot System Status",
            description="```diff\n+ SYSTEM ONLINE\n+ ALL SERVICES OPERATIONAL\n```",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Server & User Statistics
        announcement_embed.add_field(
            name="📊 Network Statistics",
            value=f"```yaml\n"
                  f"Servers      : {len(self.bot.guilds):,}\n"
                  f"Total Users  : {sum(g.member_count for g in self.bot.guilds):,}\n"
                  f"Registered   : {total_users:,}\n"
                  f"Active (24h) : {active_users_today:,}\n"
                  f"Active (7d)  : {active_users_week:,}\n"
                  f"Blacklisted  : {blacklisted_users:,}\n"
                  f"```",
            inline=True
        )
        
        # Cookie Statistics
        announcement_embed.add_field(
            name="🍪 Cookie Analytics",
            value=f"```yaml\n"
                  f"Total Claims : {total_cookies_claimed.get('all_time_claims', 0) if total_cookies_claimed else 0:,}\n"
                  f"Claims (24h) : {recent_claims:,}\n"
                  f"Total Stock  : {total_stock:,} files\n"
                  f"Cookie Types : {len(stock_info)}\n"
                  f"Avg Claims   : {(total_cookies_claimed.get('all_time_claims', 0) // max(total_users, 1)) if total_cookies_claimed else 0}/user\n"
                  f"```",
            inline=True
        )
        
        # Stock Overview
        stock_text = "```diff\n"
        for cookie, count in sorted(stock_info.items(), key=lambda x: x[1], reverse=True)[:8]:
            if count > 20:
                stock_text += f"+ {cookie.ljust(12)}: {count:>3} ✓\n"
            elif count > 10:
                stock_text += f"! {cookie.ljust(12)}: {count:>3} ⚠\n"
            elif count > 0:
                stock_text += f"- {cookie.ljust(12)}: {count:>3} ⚠\n"
            else:
                stock_text += f"- {cookie.ljust(12)}: OUT ✗\n"
        stock_text += "```"
        
        announcement_embed.add_field(
            name="📦 Cookie Stock Levels",
            value=stock_text,
            inline=False
        )
        
        # Top Cookies
        if top_cookies:
            top_text = "```yaml\n"
            for i, (name, count) in enumerate(top_cookies, 1):
                top_text += f"{i}. {name.ljust(12)}: {count:,} claims\n"
            top_text += "```"
            
            announcement_embed.add_field(
                name="🏆 Most Popular Cookies",
                value=top_text,
                inline=True
            )
        
        # System Performance
        announcement_embed.add_field(
            name="💻 System Performance",
            value=f"```yaml\n"
                  f"Latency  : {round(self.bot.latency * 1000)}ms\n"
                  f"RAM      : {psutil.virtual_memory().percent}%\n"
                  f"CPU      : {psutil.cpu_percent()}%\n"
                  f"Uptime   : {self.bot.get_uptime()}\n"
                  f"Commands : {len(self.bot.commands)}\n"
                  f"```",
            inline=True
        )
        
        announcement_embed.set_thumbnail(url=self.bot.user.avatar.url)
        announcement_embed.set_footer(text="Cookie Bot v2.0 | Premium Edition | Auto-refresh available")
        
        # Update message
        await interaction.followup.edit_message(
            message_id=self.message.id,
            embed=announcement_embed,
            view=self
        )