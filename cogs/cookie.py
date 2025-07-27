# cogs/cookie.py

import discord
from discord.ext import commands, tasks
import os
import random
from datetime import datetime, timedelta, timezone
import asyncio
import json
from typing import Optional, Dict, List

class CookieView(discord.ui.View):
    def __init__(self, cookies: Dict, user_points: int):
        super().__init__(timeout=60)
        self.cookies = cookies
        self.user_points = user_points
        self.selected_cookie = None
        
        options = []
        for cookie_type, config in cookies.items():
            if not config.get("enabled", True):
                continue
            emoji = self.get_cookie_emoji(cookie_type)
            options.append(
                discord.SelectOption(
                    label=cookie_type.title(),
                    value=cookie_type,
                    description=f"💰 {config['cost']} pts • ⏰ {config['cooldown']}h",
                    emoji=emoji
                )
            )
        
        self.select = discord.ui.Select(
            placeholder="🍪 Choose a cookie type...",
            options=options[:25]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
    def get_cookie_emoji(self, cookie_type: str) -> str:
        emojis = {
            "netflix": "🎬", "spotify": "🎵", "prime": "📦",
            "jiohotstar": "⭐", "tradingview": "📈", "chatgpt": "🤖",
            "claude": "🧠", "peacock": "🦚", "crunchyroll": "🍙",
            "canalplus": "📺"
        }
        return emojis.get(cookie_type, "🍪")
    
    async def select_callback(self, interaction: discord.Interaction):
        self.selected_cookie = self.select.values[0]
        cookie = self.cookies[self.selected_cookie]
        
        embed = discord.Embed(
            title=f"{self.get_cookie_emoji(self.selected_cookie)} {self.selected_cookie.title()} Cookie",
            color=0x5865F2
        )
        embed.add_field(name="💰 Cost", value=f"```{cookie['cost']} points```", inline=True)
        embed.add_field(name="⏰ Cooldown", value=f"```{cookie['cooldown']} hours```", inline=True)
        embed.add_field(name="💳 Your Balance", value=f"```{self.user_points} points```", inline=True)
        
        if self.user_points >= cookie['cost']:
            embed.description = "✅ Click confirm to claim this cookie!"
            embed.color = 0x00ff00
            
            self.clear_items()
            self.add_item(discord.ui.Button(label="✅ Confirm", style=discord.ButtonStyle.success, custom_id="confirm"))
            self.add_item(discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel"))
        else:
            embed.description = f"❌ You need **{cookie['cost'] - self.user_points}** more points!"
            embed.color = 0xff0000
            embed.add_field(
                name="💡 How to get points?",
                value="• `/daily` - Claim daily points\n• `/invite` - Invite friends\n• Boost the server",
                inline=False
            )
            
        await interaction.response.edit_message(embed=embed, view=self)
        
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class FeedbackModal(discord.ui.Modal, title="🍪 Cookie Feedback"):
    def __init__(self, cookie_type: str):
        super().__init__()
        self.cookie_type = cookie_type
        
        self.rating = discord.ui.TextInput(
            label="Rate your experience (1-5)",
            placeholder="Enter a number from 1 to 5",
            required=True,
            max_length=1
        )
        self.add_item(self.rating)
        
        self.feedback = discord.ui.TextInput(
            label="Your feedback",
            style=discord.TextStyle.paragraph,
            placeholder="Tell us about your experience...",
            required=True,
            max_length=500
        )
        self.add_item(self.feedback)
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating.value)
            if rating < 1 or rating > 5:
                raise ValueError
        except:
            await interaction.response.send_message("❌ Invalid rating! Please use a number from 1-5.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="✅ Feedback Submitted!",
            description=f"Thank you for your feedback on **{self.cookie_type}** cookie!",
            color=0x00ff00
        )
        embed.add_field(name="⭐ Rating", value="⭐" * rating, inline=True)
        embed.add_field(name="🏆 Reward", value="+2 trust score", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CookieCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_feedback_deadlines.start()
        self.update_cookie_prices.start()
        
    def cog_unload(self):
        self.check_feedback_deadlines.cancel()
        self.update_cookie_prices.cancel()
        
    async def get_or_create_user(self, user_id: int, username: str):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "username": username,
                "points": 0,
                "total_earned": 0,
                "total_spent": 0,
                "trust_score": 50,
                "level": 1,
                "xp": 0,
                "badges": [],
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "daily_claimed": None,
                "daily_streak": 0,
                "invite_count": 0,
                "last_claim": None,
                "cookie_claims": {},
                "weekly_claims": 0,
                "total_claims": 0,
                "blacklisted": False,
                "blacklist_expires": None,
                "premium_until": None,
                "favorite_cookie": None
            }
            await self.db.users.insert_one(user)
        else:
            await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_active": datetime.now(timezone.utc)}}
            )
        return user
    
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        try:
            server = await self.db.servers.find_one({"server_id": guild_id})
            if not server:
                return
                
            log_channel_id = server["channels"].get("log")
            if log_channel_id:
                channel = self.bot.get_channel(log_channel_id)
                if channel:
                    embed = discord.Embed(
                        description=message,
                        color=color,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_footer(text="Cookie Bot Logs")
                    await channel.send(embed=embed)
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            main_server_id = config.get("main_server_id")
            if config and config.get("main_log_channel") and guild_id != main_server_id:
                main_log = self.bot.get_channel(config["main_log_channel"])
                if main_log:
                    guild = self.bot.get_guild(guild_id)
                    embed = discord.Embed(
                        title="📝 Activity Log",
                        description=message,
                        color=color,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.set_footer(text=f"{guild.name if guild else 'Unknown'}", icon_url=guild.icon.url if guild and guild.icon else None)
                    await main_log.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Error logging action: {e}")
    
    async def update_statistics(self, cookie_type: str, user_id: int):
        try:
            await self.db.statistics.update_one(
                {"_id": "global_stats"},
                {
                    "$inc": {
                        f"weekly_claims.{cookie_type}": 1,
                        f"total_claims.{cookie_type}": 1,
                        "all_time_claims": 1
                    }
                },
                upsert=True
            )
        except Exception as e:
            self.bot.logger.error(f"Error updating statistics: {e}")
    
    async def check_maintenance(self, ctx) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        owner_id = config.get("owner_id")
        if config.get("maintenance_mode") and ctx.author.id != owner_id:
            embed = discord.Embed(
                title="🔧 Maintenance Mode",
                description="Bot is currently under maintenance. Please try again later!",
                color=0xffa500
            )
            embed.set_footer(text="We'll be back soon!")
            await ctx.send(embed=embed, ephemeral=True)
            return False
        return True
    
    async def check_blacklist(self, user_id: int) -> tuple[bool, datetime]:
        user = await self.db.users.find_one({"user_id": user_id})
        if not user or not user.get("blacklisted"):
            return False, None
            
        if user.get("blacklist_expires"):
            if datetime.now(timezone.utc) > user["blacklist_expires"]:
                await self.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"blacklisted": False, "blacklist_expires": None}}
                )
                return False, None
            return True, user["blacklist_expires"]
        return True, None
    
    async def get_user_cooldown(self, user: discord.Member, server: dict, cookie_type: str) -> int:
        if not server.get("role_based"):
            return server["cookies"][cookie_type]["cooldown"]
        
        min_cooldown = server["cookies"][cookie_type]["cooldown"]
        
        for role in user.roles:
            role_config = server["roles"].get(str(role.id))
            if role_config:
                if "all" in role_config["access"] or cookie_type in role_config["access"]:
                    min_cooldown = min(min_cooldown, role_config["cooldown"])
        
        return min_cooldown
    
    async def get_user_cost(self, user: discord.Member, server: dict, cookie_type: str) -> int:
        if not server.get("role_based"):
            return server["cookies"][cookie_type]["cost"]
        
        min_cost = server["cookies"][cookie_type]["cost"]
        
        for role in user.roles:
            role_config = server["roles"].get(str(role.id))
            if role_config:
                if "all" in role_config["access"] or cookie_type in role_config["access"]:
                    if role_config["cost"] != "default":
                        min_cost = min(min_cost, role_config["cost"])
        
        return min_cost
    
    @tasks.loop(minutes=5)
    async def check_feedback_deadlines(self):
        try:
            now = datetime.now(timezone.utc)
            
            async for user in self.db.users.find({
                "last_claim": {"$exists": True},
                "last_claim.feedback_given": False,
                "blacklisted": False
            }):
                last_claim = user.get("last_claim")
                if last_claim and last_claim.get("feedback_deadline"):
                    if now > last_claim["feedback_deadline"]:
                        await self.db.users.update_one(
                            {"user_id": user["user_id"]},
                            {
                                "$set": {
                                    "blacklisted": True,
                                    "blacklist_expires": now + timedelta(days=30)
                                }
                            }
                        )
                        
                        guild_id = last_claim.get("server_id")
                        if guild_id:
                            await self.log_action(
                                guild_id,
                                f"🚫 <@{user['user_id']}> auto-blacklisted for not providing feedback",
                                discord.Color.red()
                            )
        except Exception as e:
            self.bot.logger.error(f"Error in feedback check: {e}")
    
    @tasks.loop(hours=24)
    async def update_cookie_prices(self):
        try:
            async for server in self.db.servers.find({"dynamic_pricing": True}):
                for cookie_type in server["cookies"]:
                    stats = await self.db.statistics.find_one({"_id": "global_stats"})
                    claims = stats.get("weekly_claims", {}).get(cookie_type, 0)
                    
                    base_cost = server["cookies"][cookie_type]["base_cost"]
                    if claims > 100:
                        new_cost = int(base_cost * 1.2)
                    elif claims < 20:
                        new_cost = int(base_cost * 0.8)
                    else:
                        new_cost = base_cost
                    
                    await self.db.servers.update_one(
                        {"server_id": server["server_id"]},
                        {"$set": {f"cookies.{cookie_type}.cost": new_cost}}
                    )
        except Exception as e:
            self.bot.logger.error(f"Error updating prices: {e}")

    @commands.hybrid_command(name="cookie", description="Claim a cookie with modern UI")
    async def cookie(self, ctx):
        try:
            if not await self.check_maintenance(ctx):
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                embed = discord.Embed(
                    title="❌ Server Not Setup",
                    description="This server needs to be configured first!\nAsk an admin to run `/setup`",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
                
            if not server.get("enabled"):
                embed = discord.Embed(
                    title="❌ Bot Disabled",
                    description="Cookie Bot is currently disabled in this server!",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            cookie_channel = server["channels"].get("cookie")
            if cookie_channel and ctx.channel.id != cookie_channel:
                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Please use <#{cookie_channel}> for cookie commands!",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            blacklisted, expires = await self.check_blacklist(ctx.author.id)
            if blacklisted:
                embed = discord.Embed(
                    title="🚫 Blacklisted",
                    description=f"You are blacklisted until <t:{int(expires.timestamp())}:R>",
                    color=0xff0000
                )
                embed.add_field(
                    name="📞 Appeal",
                    value=f"[Join support server]({os.getenv('MAIN_SERVER_INVITE')}) to appeal",
                    inline=False
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.get_or_create_user(ctx.author.id, str(ctx.author))
            
            embed = discord.Embed(
                title="🍪 Cookie Store",
                description="Select a cookie type from the dropdown below!",
                color=0x5865F2
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.add_field(name="💰 Your Points", value=f"```{user_data['points']}```", inline=True)
            embed.add_field(name="⭐ Trust Score", value=f"```{user_data['trust_score']}/100```", inline=True)
            embed.add_field(name="🎯 Level", value=f"```Level {user_data.get('level', 1)}```", inline=True)
            embed.set_footer(text="⏰ Selection expires in 60 seconds")
            
            view = CookieView(server["cookies"], user_data["points"])
            message = await ctx.send(embed=embed, view=view)
            
            async def button_callback(interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
                    return
                
                if interaction.data["custom_id"] == "confirm" and view.selected_cookie:
                    await self.process_cookie_claim(interaction, ctx.author, view.selected_cookie, server, user_data, message)
                else:
                    embed = discord.Embed(
                        title="❌ Cancelled",
                        description="Cookie claim cancelled!",
                        color=0xff0000
                    )
                    await interaction.response.edit_message(embed=embed, view=None)
            
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.callback = button_callback
                    
        except Exception as e:
            self.bot.logger.error(f"Error in cookie command: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An unexpected error occurred! Please try again.",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
    
    async def process_cookie_claim(self, interaction, user, cookie_type, server, user_data, message):
        try:
            cooldown_hours = await self.get_user_cooldown(user, server, cookie_type)
            
            if user_data.get("last_claim"):
                last_claim = user_data["last_claim"]
                if last_claim.get("type") == cookie_type:
                    time_passed = datetime.now(timezone.utc) - last_claim["date"]
                    if time_passed < timedelta(hours=cooldown_hours):
                        remaining = timedelta(hours=cooldown_hours) - time_passed
                        hours = int(remaining.total_seconds() // 3600)
                        minutes = int((remaining.total_seconds() % 3600) // 60)
                        
                        embed = discord.Embed(
                            title="⏰ Cooldown Active",
                            description=f"You can claim another **{cookie_type}** cookie in:",
                            color=0xffa500
                        )
                        embed.add_field(name="⏱️ Time Remaining", value=f"```{hours}h {minutes}m```", inline=True)
                        embed.add_field(name="💡 Tip", value="Try claiming a different cookie type!", inline=True)
                        await interaction.response.edit_message(embed=embed, view=None)
                        return
            
            cost = await self.get_user_cost(user, server, cookie_type)
            cookie_config = server["cookies"][cookie_type]
            
            directory = cookie_config["directory"]
            if not os.path.exists(directory):
                embed = discord.Embed(
                    title="❌ Configuration Error",
                    description="Cookie directory not found! Contact an admin.",
                    color=0xff0000
                )
                await interaction.response.edit_message(embed=embed, view=None)
                await self.log_action(server["server_id"], f"❌ Directory not found for {cookie_type}: {directory}", discord.Color.red())
                return
            
            files = [f for f in os.listdir(directory) if f.endswith('.txt')]
            if not files:
                embed = discord.Embed(
                    title="❌ Out of Stock",
                    description=f"No **{cookie_type}** cookies available right now!",
                    color=0xff0000
                )
                embed.add_field(name="💡 Try Later", value="Stock is refilled regularly", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)
                return
            
            selected_file = random.choice(files)
            file_path = os.path.join(directory, selected_file)
            
            embed = discord.Embed(
                title="⏳ Processing...",
                description="Preparing your cookie...",
                color=0x5865F2
            )
            await interaction.response.edit_message(embed=embed, view=None)
            
            try:
                cookie_embed = discord.Embed(
                    title=f"🍪 {cookie_type.upper()} Cookie Delivered!",
                    color=0x00ff00,
                    timestamp=datetime.now(timezone.utc)
                )
                cookie_embed.add_field(name="📁 File", value=f"`{selected_file}`", inline=True)
                cookie_embed.add_field(name="💰 Cost", value=f"`{cost} points`", inline=True)
                cookie_embed.add_field(
                    name="⚠️ IMPORTANT",
                    value=f"Submit feedback in <#{server['channels']['feedback']}> within **15 minutes** or face **30-day blacklist**!",
                    inline=False
                )
                cookie_embed.set_footer(text="Cookie Bot Premium", icon_url=self.bot.user.display_avatar.url)
                
                dm_message = await user.send(embed=cookie_embed, file=discord.File(file_path))
                
                config = await self.db.config.find_one({"_id": "bot_config"})
                feedback_deadline = datetime.now(timezone.utc) + timedelta(minutes=config.get("feedback_minutes", 15))
                
                await self.db.users.update_one(
                    {"user_id": user.id},
                    {
                        "$set": {
                            "points": user_data["points"] - cost,
                            "last_claim": {
                                "date": datetime.now(timezone.utc),
                                "type": cookie_type,
                                "file": selected_file,
                                "server_id": server["server_id"],
                                "feedback_deadline": feedback_deadline,
                                "feedback_given": False
                            }
                        },
                        "$inc": {
                            "total_spent": cost,
                            f"cookie_claims.{cookie_type}": 1,
                            "weekly_claims": 1,
                            "total_claims": 1,
                            "xp": 10
                        }
                    }
                )
                
                await self.update_statistics(cookie_type, user.id)
                
                success_embed = discord.Embed(
                    title="✅ Cookie Sent!",
                    description=f"Your **{cookie_type}** cookie has been sent to your DMs!",
                    color=0x00ff00
                )
                success_embed.add_field(name="💰 Cost", value=f"`-{cost} points`", inline=True)
                success_embed.add_field(name="💳 New Balance", value=f"`{user_data['points'] - cost} points`", inline=True)
                success_embed.add_field(name="⏰ Cooldown", value=f"`{cooldown_hours} hours`", inline=True)
                success_embed.add_field(
                    name="⚠️ Remember",
                    value=f"Submit feedback in <#{server['channels']['feedback']}> within **15 minutes**!",
                    inline=False
                )
                
                await message.edit(embed=success_embed, view=None)
                
                await self.log_action(
                    server["server_id"],
                    f"🍪 {user.mention} claimed **{cookie_type}** cookie (`{selected_file}`) [-{cost} points]",
                    discord.Color.green()
                )
                
            except discord.Forbidden:
                error_embed = discord.Embed(
                    title="❌ DM Failed",
                    description="I couldn't send you a DM!",
                    color=0xff0000
                )
                error_embed.add_field(
                    name="🔧 Fix This",
                    value="• Enable DMs from server members\n• Make sure you haven't blocked the bot\n• Check your privacy settings",
                    inline=False
                )
                await message.edit(embed=error_embed, view=None)
                
        except Exception as e:
            self.bot.logger.error(f"Error processing cookie claim: {e}")
            error_embed = discord.Embed(
                title="❌ Error",
                description="Failed to process your cookie claim!",
                color=0xff0000
            )
            await interaction.response.edit_message(embed=error_embed, view=None)

    @commands.hybrid_command(name="stock", description="Check cookie stock with modern UI")
    async def stock(self, ctx, cookie_type: str = None):
        try:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                embed = discord.Embed(
                    title="❌ Not Configured",
                    description="Server not configured!",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 Cookie Stock Status",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
            
            if cookie_type:
                cookie_type = cookie_type.lower()
                if cookie_type not in server["cookies"]:
                    embed = discord.Embed(
                        title="❌ Invalid Type",
                        description=f"Cookie type `{cookie_type}` not found!",
                        color=0xff0000
                    )
                    await ctx.send(embed=embed, ephemeral=True)
                    return
                    
                cookie_config = server["cookies"][cookie_type]
                directory = cookie_config["directory"]
                
                if os.path.exists(directory):
                    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                    count = len(files)
                    
                    if count > 50:
                        status = "🟢 Fully Stocked"
                        color = 0x00ff00
                    elif count > 20:
                        status = "🟡 Good Stock"
                        color = 0xffa500
                    elif count > 0:
                        status = "🟠 Low Stock"
                        color = 0xff6600
                    else:
                        status = "🔴 Out of Stock"
                        color = 0xff0000
                    
                    embed.color = color
                    embed.add_field(name="🍪 Type", value=cookie_type.title(), inline=True)
                    embed.add_field(name="📊 Count", value=f"```{count} files```", inline=True)
                    embed.add_field(name="📈 Status", value=status, inline=True)
                    embed.add_field(name="💰 Cost", value=f"```{cookie_config['cost']} points```", inline=True)
                    embed.add_field(name="⏰ Cooldown", value=f"```{cookie_config['cooldown']} hours```", inline=True)
                    embed.add_field(name="✅ Enabled", value="Yes" if cookie_config.get("enabled", True) else "No", inline=True)
                else:
                    embed.description = "❌ Directory not found"
                    embed.color = 0xff0000
            else:
                total_stock = 0
                stock_data = []
                
                for cookie_type, cookie_config in server["cookies"].items():
                    if not cookie_config.get("enabled", True):
                        continue
                        
                    directory = cookie_config["directory"]
                    if os.path.exists(directory):
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        count = len(files)
                        total_stock += count
                        
                        if count > 50:
                            emoji = "🟢"
                        elif count > 20:
                            emoji = "🟡"
                        elif count > 0:
                            emoji = "🟠"
                        else:
                            emoji = "🔴"
                        
                        stock_data.append((cookie_type, count, emoji))
                
                embed.description = f"Total cookies in stock: **{total_stock}**"
                
                for i, (cookie_type, count, emoji) in enumerate(sorted(stock_data, key=lambda x: x[1], reverse=True)):
                    if i < 10:
                        embed.add_field(
                            name=f"{emoji} {cookie_type.title()}",
                            value=f"```{count} files```",
                            inline=True
                        )
                
                legend = "🟢 Full | 🟡 Good | 🟠 Low | 🔴 Empty"
                embed.add_field(name="📊 Legend", value=legend, inline=False)
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.bot.logger.error(f"Error in stock command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="feedback", description="Submit feedback with modern UI")
    async def feedback(self, ctx):
        try:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            feedback_channel = server["channels"].get("feedback")
            if feedback_channel and ctx.channel.id != feedback_channel:
                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Please use <#{feedback_channel}> for feedback!",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            if not user_data or not user_data.get("last_claim"):
                embed = discord.Embed(
                    title="❌ No Recent Claims",
                    description="You haven't claimed any cookies recently!",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            if last_claim.get("feedback_given"):
                embed = discord.Embed(
                    title="✅ Already Submitted",
                    description="You already submitted feedback for your last cookie!",
                    color=0x00ff00
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            if datetime.now(timezone.utc) > last_claim["feedback_deadline"]:
                embed = discord.Embed(
                    title="❌ Deadline Expired",
                    description="Feedback deadline has passed! You might be blacklisted.",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            modal = FeedbackModal(last_claim["type"])
            await ctx.interaction.response.send_modal(modal)
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$set": {"last_claim.feedback_given": True},
                    "$inc": {"trust_score": 2, "xp": 5}
                }
            )
            
            await self.log_action(
                ctx.guild.id,
                f"📸 {ctx.author.mention} submitted feedback for **{last_claim['type']}** cookie",
                discord.Color.green()
            )
            
        except Exception as e:
            self.bot.logger.error(f"Error in feedback command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        if message.attachments and message.channel.type == discord.ChannelType.text:
            server = await self.db.servers.find_one({"server_id": message.guild.id})
            if server and message.channel.id == server["channels"].get("feedback"):
                user_data = await self.db.users.find_one({"user_id": message.author.id})
                if user_data and user_data.get("last_claim") and not user_data["last_claim"].get("feedback_given"):
                    await self.db.users.update_one(
                        {"user_id": message.author.id},
                        {
                            "$set": {"last_claim.feedback_given": True},
                            "$inc": {"trust_score": 3, "xp": 10}
                        }
                    )
                    
                    await message.add_reaction("✅")
                    
                    embed = discord.Embed(
                        title="✅ Screenshot Verified!",
                        description=f"{message.author.mention} Thank you for the feedback screenshot!",
                        color=0x00ff00
                    )
                    embed.add_field(name="🏆 Rewards", value="+3 trust score\n+10 XP", inline=True)
                    
                    msg = await message.channel.send(embed=embed)
                    await asyncio.sleep(10)
                    await msg.delete()

async def setup(bot):
    await bot.add_cog(CookieCog(bot))