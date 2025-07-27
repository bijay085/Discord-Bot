# cogs/cookie.py

import discord
from discord.ext import commands, tasks
import os
import random
from datetime import datetime, timedelta, timezone
import traceback
import re
import hashlib

class CookieCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_feedback_deadlines.start()
        self.rate_limits = {}
        self.suspicious_cache = {}
        
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
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "daily_claimed": None,
                "invite_count": 0,
                "last_claim": None,
                "cookie_claims": {},
                "weekly_claims": 0,
                "total_claims": 0,
                "blacklisted": False,
                "blacklist_expires": None,
                "failed_attempts": 0,
                "last_failed_attempt": None
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
                    await channel.send(embed=embed)
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            main_server_id = config.get("main_server_id")
            if config and config.get("main_log_channel") and guild_id != main_server_id:
                main_log = self.bot.get_channel(config["main_log_channel"])
                if main_log:
                    guild = self.bot.get_guild(guild_id)
                    embed = discord.Embed(
                        description=f"**{guild.name if guild else 'Unknown'}**: {message}",
                        color=color,
                        timestamp=datetime.now(timezone.utc)
                    )
                    await main_log.send(embed=embed)
        except Exception as e:
            print(f"Error logging action: {e}")
    
    async def check_user_filters(self, ctx, user: discord.Member) -> tuple[bool, str]:
        config = await self.db.config.find_one({"_id": "bot_config"})
        if not config:
            config = {
                "min_account_age_days": 7,
                "min_server_days": 1,
                "min_trust_score": 20,
                "rate_limit_claims": 3,
                "rate_limit_window": 60,
                "max_failed_attempts": 5,
                "suspicious_username_patterns": ["test", "bot", "spam", "fake", "temp", "throwaway"],
                "require_avatar": True,
                "require_verified_email": False,
                "min_message_count": 0
            }
        
        # Account age check
        account_age = datetime.now(timezone.utc) - user.created_at.replace(tzinfo=timezone.utc)
        if account_age < timedelta(days=config.get("min_account_age_days", 7)):
            await self.log_failed_attempt(user.id, "Account too new")
            return False, f"❌ Your account must be at least **{config.get('min_account_age_days', 7)}** days old to claim cookies.\nYour account age: **{account_age.days}** days"
        
        # Server join age check
        if user.joined_at:
            server_age = datetime.now(timezone.utc) - user.joined_at.replace(tzinfo=timezone.utc)
            if server_age < timedelta(days=config.get("min_server_days", 1)):
                await self.log_failed_attempt(user.id, "Joined server too recently")
                return False, f"❌ You must be in the server for at least **{config.get('min_server_days', 1)}** days to claim cookies.\nYou joined: **{server_age.days}** days ago"
        
        # Avatar check
        if config.get("require_avatar", True) and not user.avatar:
            await self.log_failed_attempt(user.id, "No avatar")
            return False, "❌ You must have a profile avatar to claim cookies."
        
        # Suspicious username check
        patterns = config.get("suspicious_username_patterns", [])
        username_lower = user.name.lower()
        for pattern in patterns:
            if pattern.lower() in username_lower:
                await self.log_failed_attempt(user.id, f"Suspicious username: {pattern}")
                return False, "❌ Your username has been flagged as suspicious. Please contact an admin."
        
        # Excessive numbers in username
        if len(re.findall(r'\d', user.name)) > len(user.name) * 0.5:
            await self.log_failed_attempt(user.id, "Too many numbers in username")
            return False, "❌ Your username contains too many numbers."
        
        # Trust score check
        user_data = await self.db.users.find_one({"user_id": user.id})
        if user_data:
            trust_score = user_data.get("trust_score", 50)
            if trust_score < config.get("min_trust_score", 20):
                return False, f"❌ Your trust score is too low ({trust_score}/100). Minimum required: {config.get('min_trust_score', 20)}"
            
            # Failed attempts check
            failed_attempts = user_data.get("failed_attempts", 0)
            if failed_attempts >= config.get("max_failed_attempts", 5):
                last_failed = user_data.get("last_failed_attempt")
                if last_failed and datetime.now(timezone.utc) - last_failed < timedelta(hours=24):
                    return False, "❌ Too many failed attempts. Please try again in 24 hours."
        
        # Rate limit check
        rate_check = await self.check_rate_limit(user.id)
        if not rate_check[0]:
            return False, f"❌ Rate limit exceeded. Please wait {rate_check[1]} before trying again."
        
        # Duplicate device check (using hash of user ID pattern)
        device_hash = self.get_device_fingerprint(user)
        if device_hash in self.suspicious_cache:
            last_seen = self.suspicious_cache[device_hash]
            if datetime.now(timezone.utc) - last_seen < timedelta(minutes=30):
                await self.log_failed_attempt(user.id, "Duplicate device detected")
                return False, "❌ Multiple accounts detected from same device. This has been logged."
        
        self.suspicious_cache[device_hash] = datetime.now(timezone.utc)
        
        return True, "Passed all filters"
    
    async def log_failed_attempt(self, user_id: int, reason: str):
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"failed_attempts": 1},
                "$set": {"last_failed_attempt": datetime.now(timezone.utc)},
                "$push": {
                    "failed_attempt_log": {
                        "timestamp": datetime.now(timezone.utc),
                        "reason": reason
                    }
                }
            }
        )
    
    def get_device_fingerprint(self, user: discord.Member) -> str:
        data = f"{user.created_at.timestamp()}-{user.discriminator}-{len(user.name)}"
        return hashlib.md5(data.encode()).hexdigest()[:8]
    
    async def check_rate_limit(self, user_id: int) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        config = await self.db.config.find_one({"_id": "bot_config"})
        
        window = config.get("rate_limit_window", 60)
        max_claims = config.get("rate_limit_claims", 3)
        
        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = []
        
        self.rate_limits[user_id] = [
            timestamp for timestamp in self.rate_limits[user_id]
            if now - timestamp < timedelta(minutes=window)
        ]
        
        if len(self.rate_limits[user_id]) >= max_claims:
            oldest = min(self.rate_limits[user_id])
            time_until_reset = timedelta(minutes=window) - (now - oldest)
            minutes = int(time_until_reset.total_seconds() // 60)
            seconds = int(time_until_reset.total_seconds() % 60)
            return False, f"{minutes}m {seconds}s"
        
        self.rate_limits[user_id].append(now)
        return True, ""
    
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
                }
            )
        except Exception as e:
            print(f"Error updating statistics: {e}")
    
    async def check_maintenance(self, ctx) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        owner_id = config.get("owner_id")
        if config.get("maintenance_mode") and ctx.author.id != owner_id:
            await ctx.send("⚠️ Bot is under maintenance. Please try again later.", ephemeral=True)
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
                                },
                                "$inc": {"trust_score": -10}
                            }
                        )
                        
                        guild_id = last_claim.get("server_id")
                        if guild_id:
                            await self.log_action(
                                guild_id,
                                f"🚫 <@{user['user_id']}> blacklisted for not providing feedback (Trust: -10)",
                                discord.Color.red()
                            )
        except Exception as e:
            print(f"Error in feedback check: {e}")

    @commands.hybrid_command(name="cookie", description="Claim a cookie")
    async def cookie(self, ctx, type: str):
        try:
            if not await self.check_maintenance(ctx):
                return
            
            # Run all filters first
            filter_passed, filter_message = await self.check_user_filters(ctx, ctx.author)
            if not filter_passed:
                await ctx.send(filter_message, ephemeral=True)
                await self.log_action(
                    ctx.guild.id,
                    f"🚫 {ctx.author.mention} failed filter check: {filter_message.split('.')[0]}",
                    discord.Color.orange()
                )
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured! Ask an admin to run setup.", ephemeral=True)
                return
                
            if not server.get("enabled"):
                await ctx.send("❌ Bot is disabled in this server!", ephemeral=True)
                return
            
            cookie_channel = server["channels"].get("cookie")
            if cookie_channel and ctx.channel.id != cookie_channel:
                await ctx.send(f"❌ Please use <#{cookie_channel}> for cookie commands!", ephemeral=True)
                return
            
            blacklisted, expires = await self.check_blacklist(ctx.author.id)
            if blacklisted:
                await ctx.send(f"❌ You are blacklisted until <t:{int(expires.timestamp())}:R>", ephemeral=True)
                return
            
            type = type.lower()
            if type not in server["cookies"]:
                available = [c for c, cfg in server["cookies"].items() if cfg.get("enabled", True)]
                await ctx.send(f"❌ Invalid cookie type!\nAvailable: `{', '.join(available)}`", ephemeral=True)
                return
            
            cookie_config = server["cookies"][type]
            if not cookie_config.get("enabled", True):
                await ctx.send(f"❌ {type} cookies are currently disabled!", ephemeral=True)
                return
            
            user_data = await self.get_or_create_user(ctx.author.id, str(ctx.author))
            
            cooldown_hours = await self.get_user_cooldown(ctx.author, server, type)
            
            if user_data.get("last_claim"):
                last_claim = user_data["last_claim"]
                if last_claim.get("type") == type:
                    time_passed = datetime.now(timezone.utc) - last_claim["date"]
                    if time_passed < timedelta(hours=cooldown_hours):
                        remaining = timedelta(hours=cooldown_hours) - time_passed
                        hours = int(remaining.total_seconds() // 3600)
                        minutes = int((remaining.total_seconds() % 3600) // 60)
                        await ctx.send(f"⏰ Cooldown active! Try again in **{hours}h {minutes}m**", ephemeral=True)
                        return
            
            cost = await self.get_user_cost(ctx.author, server, type)
            
            if user_data["points"] < cost:
                await ctx.send(
                    f"❌ Not enough points!\nYou need: **{cost}** points\nYou have: **{user_data['points']}** points\n\nUse `/daily` or `/getpoints`",
                    ephemeral=True
                )
                return
            
            directory = cookie_config["directory"]
            if not os.path.exists(directory):
                await ctx.send("❌ Cookie directory not configured! Contact an admin.", ephemeral=True)
                await self.log_action(ctx.guild.id, f"❌ Directory not found for {type}: {directory}", discord.Color.red())
                return
            
            files = [f for f in os.listdir(directory) if f.endswith('.txt')]
            if not files:
                await ctx.send(f"❌ No {type} cookies in stock! Try again later.", ephemeral=True)
                return
            
            selected_file = random.choice(files)
            file_path = os.path.join(directory, selected_file)
            
            await ctx.send(f"✅ Processing your {type} cookie request...", ephemeral=True)
            
            try:
                dm_message = await ctx.author.send(
                    f"🍪 **{type.upper()} Cookie**\n"
                    f"📁 File: `{selected_file}`\n\n"
                    f"⚠️ **IMPORTANT**: Submit feedback in <#{server['channels']['feedback']}> within **15 minutes** or you'll be **blacklisted for 30 days**!",
                    file=discord.File(file_path)
                )
                
                config = await self.db.config.find_one({"_id": "bot_config"})
                feedback_deadline = datetime.now(timezone.utc) + timedelta(minutes=config.get("feedback_minutes", 15))
                
                await self.db.users.update_one(
                    {"user_id": ctx.author.id},
                    {
                        "$set": {
                            "points": user_data["points"] - cost,
                            "last_claim": {
                                "date": datetime.now(timezone.utc),
                                "type": type,
                                "file": selected_file,
                                "server_id": ctx.guild.id,
                                "feedback_deadline": feedback_deadline,
                                "feedback_given": False
                            },
                            "failed_attempts": 0
                        },
                        "$inc": {
                            "total_spent": cost,
                            f"cookie_claims.{type}": 1,
                            "weekly_claims": 1,
                            "total_claims": 1,
                            "trust_score": 1
                        }
                    }
                )
                
                await self.update_statistics(type, ctx.author.id)
                
                await ctx.edit_original_response(
                    content=f"✅ **{type}** cookie sent to your DMs!\n"
                    f"💰 -{cost} points | Balance: **{user_data['points'] - cost}** points\n"
                    f"⏰ Submit feedback in <#{server['channels']['feedback']}> within **15 minutes**!"
                )
                
                await self.log_action(
                    ctx.guild.id,
                    f"🍪 {ctx.author.mention} claimed **{type}** cookie (`{selected_file}`) [-{cost} points] [Trust: {user_data.get('trust_score', 50) + 1}]",
                    discord.Color.green()
                )
                
            except discord.Forbidden:
                await ctx.edit_original_response(
                    content="❌ **I can't send you a DM!**\n\n"
                    "Please check:\n"
                    "• Enable DMs from server members\n"
                    "• Make sure you haven't blocked the bot\n"
                    "• Check your privacy settings"
                )
                return
                
        except Exception as e:
            print(f"Error in cookie command: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred! Please try again or contact support.", ephemeral=True)

    @commands.hybrid_command(name="stock", description="Check cookie stock")
    async def stock(self, ctx, type: str = None):
        try:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 Cookie Stock",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if type:
                type = type.lower()
                if type not in server["cookies"]:
                    await ctx.send("❌ Invalid cookie type!", ephemeral=True)
                    return
                    
                cookie_config = server["cookies"][type]
                directory = cookie_config["directory"]
                
                if os.path.exists(directory):
                    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                    count = len(files)
                    status = "✅ Available" if count > 0 else "❌ Out of Stock"
                    
                    embed.add_field(
                        name=f"{type.title()}",
                        value=f"Stock: **{count}** files\nStatus: {status}\nCost: **{cookie_config['cost']}** points",
                        inline=False
                    )
                else:
                    embed.add_field(name=type.title(), value="❌ Directory not found", inline=False)
            else:
                for cookie_type, cookie_config in server["cookies"].items():
                    if not cookie_config.get("enabled", True):
                        continue
                        
                    directory = cookie_config["directory"]
                    if os.path.exists(directory):
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        count = len(files)
                        emoji = "✅" if count > 10 else "⚠️" if count > 0 else "❌"
                        embed.add_field(
                            name=cookie_type.title(),
                            value=f"{emoji} **{count}** files",
                            inline=True
                        )
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in stock command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="feedback", description="Submit feedback for your last cookie")
    async def feedback(self, ctx):
        try:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            feedback_channel = server["channels"].get("feedback")
            if feedback_channel and ctx.channel.id != feedback_channel:
                await ctx.send(f"❌ Please use <#{feedback_channel}> for feedback!", ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            if not user_data or not user_data.get("last_claim"):
                await ctx.send("❌ You haven't claimed any cookies recently!", ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            if last_claim.get("feedback_given"):
                await ctx.send("✅ You already submitted feedback for your last cookie!", ephemeral=True)
                return
            
            if datetime.now(timezone.utc) > last_claim["feedback_deadline"]:
                await ctx.send("❌ Feedback deadline expired! You might be blacklisted.", ephemeral=True)
                return
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$set": {"last_claim.feedback_given": True},
                    "$inc": {"trust_score": 1}
                }
            )
            
            embed = discord.Embed(
                title="✅ Feedback Received!",
                description=(
                    f"Thank you for confirming your **{last_claim['type']}** cookie works!\n"
                    f"Your trust score increased by +1"
                ),
                color=discord.Color.green()
            )
            embed.set_footer(text="Don't forget to attach a screenshot!")
            
            await ctx.send(embed=embed, ephemeral=True)
            
            await self.log_action(
                ctx.guild.id,
                f"📸 {ctx.author.mention} submitted feedback for **{last_claim['type']}** cookie",
                discord.Color.green()
            )
        except Exception as e:
            print(f"Error in feedback command: {e}")
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
                            "$inc": {"trust_score": 2}
                        }
                    )
                    
                    await message.add_reaction("✅")
                    await message.channel.send(
                        f"✅ {message.author.mention} Thank you for the feedback screenshot! +2 trust score",
                        delete_after=10
                    )

async def setup(bot):
    await bot.add_cog(CookieCog(bot))