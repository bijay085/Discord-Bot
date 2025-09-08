import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
from datetime import datetime, timedelta, timezone, time
import traceback
from typing import List, Dict, Optional
import asyncio
import aiofiles
import json

class CookieView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.response = None
        
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if self.response:
                await self.response.edit(view=self)
        except discord.NotFound:
            pass
        except Exception:
            pass
            
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This menu isn't for you!", ephemeral=True)
            return False
        return True

class CookieSelectMenu(discord.ui.Select):
    def __init__(self, server_data, user_data, member, costs_dict, access_dict, daily_limits):
        self.server_data = server_data
        self.user_data = user_data
        self.member = member
        self.costs_dict = costs_dict
        self.access_dict = access_dict
        self.daily_limits = daily_limits
        
        options = []
        for cookie_type, config in server_data["cookies"].items():
            if config.get("enabled", True) and self.access_dict.get(cookie_type, False):
                cost = self.costs_dict.get(cookie_type, config["cost"])
                can_afford = user_data["points"] >= cost
                
                daily_claimed = user_data.get("daily_claims", {}).get(cookie_type, {}).get("count", 0)
                daily_limit = self.daily_limits.get(cookie_type, -1)
                limit_reached = daily_limit != -1 and daily_claimed >= daily_limit
                
                if limit_reached:
                    emoji = "🚫"
                    status = f"Daily limit reached ({daily_claimed}/{daily_limit})"
                else:
                    emoji = "🟢" if can_afford else "🔴"
                    status = f"{cost} points | Stock: "
                    
                    directory = config["directory"]
                    stock = 0
                    if os.path.exists(directory):
                        stock = len([f for f in os.listdir(directory) if f.endswith('.txt')])
                    status += str(stock)
                
                options.append(
                    discord.SelectOption(
                        label=f"{cookie_type.title()}",
                        value=cookie_type,
                        description=status,
                        emoji=config.get("emoji", "🍪")
                    )
                )
        
        if not options:
            options.append(
                discord.SelectOption(
                    label="No cookies available",
                    value="none",
                    description="You don't have access to any cookies with your current role",
                    emoji="❌"
                )
            )
        
        super().__init__(
            placeholder="🍪 Select a cookie type...",
            options=options[:25],
            custom_id="cookie_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ You don't have access to any cookies!", ephemeral=True)
            return
            
        cookie_type = self.values[0]
        await interaction.response.defer(ephemeral=True)
        
        cog = interaction.client.get_cog("CookieCog")
        if cog:
            await cog.process_cookie_claim(interaction, cookie_type)

class CookieProgressEmbed:
    @staticmethod
    def create_claim_progress(step: int, total: int = 4):
        progress_bar = ""
        for i in range(total):
            if i < step:
                progress_bar += "🟩"
            elif i == step:
                progress_bar += "🟨"
            else:
                progress_bar += "⬜"
        
        steps = ["Validating", "Processing", "Sending", "Complete"]
        current_step = steps[min(step, len(steps)-1)]
        
        embed = discord.Embed(
            title="🍪 Cookie Claim Progress",
            description=f"**{current_step}...**\n\n{progress_bar}",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Step {step+1}/{total}")
        return embed

class CookieCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.clear_role_cache.start()
        self.reset_daily_claims.start()
        self.active_claims = {}
        self.cooldown_cache = {}
        self.role_cache = {}
        self.access_cache = {}
        
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
                "daily_claims": {},
                "weekly_claims": 0,
                "total_claims": 0,
                "blacklisted": False,
                "blacklist_expires": None,
                "invited_users": [],
                "pending_invites": 0,
                "verified_invites": 0,
                "fake_invites": 0,
                "preferences": {
                    "dm_notifications": True,
                    "claim_confirmations": True,
                    "feedback_reminders": True
                },
                "statistics": {
                    "feedback_streak": 0,
                    "perfect_ratings": 0,
                    "favorite_cookie": None
                }
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
                    embed.set_author(name="Cookie System", icon_url=self.bot.user.avatar.url)
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
            
            user_claims = await self.db.users.find_one(
                {"user_id": user_id},
                {f"cookie_claims.{cookie_type}": 1}
            )
            
            if user_claims and user_claims.get("cookie_claims", {}).get(cookie_type, 0) > 5:
                await self.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"statistics.favorite_cookie": cookie_type}}
                )
        except Exception as e:
            print(f"Error updating statistics: {e}")
    
    async def check_maintenance(self, ctx) -> bool:
        try:
            config = await self.bot.db.config.find_one({"_id": "bot_config"})
            if not config:
                return True  # Allow if no config found
                
            owner_id = config.get("owner_id")
            if config.get("maintenance_mode") and ctx.author.id != owner_id:
                embed = discord.Embed(
                    title="🔧 Maintenance Mode",
                    description="The bot is currently under maintenance.\nPlease try again later!",
                    color=discord.Color.orange()
                )
                embed.set_footer(text="We'll be back soon!")
                await ctx.send(embed=embed, ephemeral=True)
                return False
            return True
        except Exception as e:
            print(f"Error checking maintenance: {e}")
            return True  # Allow on error to prevent blocking
        
    async def check_blacklist(self, user_id: int) -> tuple[bool, datetime]:
        user = await self.db.users.find_one({"user_id": user_id})
        if not user or not user.get("blacklisted"):
            return False, None
            
        if user.get("blacklist_expires"):
            expires = user["blacklist_expires"]
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            
            if datetime.now(timezone.utc) > expires:
                await self.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"blacklisted": False, "blacklist_expires": None}}
                )
                return False, None
            return True, expires
        return True, None
    
    def clear_user_cache(self, user_id: int):
        keys_to_remove = []
        
        for key in list(self.cooldown_cache.keys()):
            if key.startswith(f"{user_id}:"):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            self.cooldown_cache.pop(key, None)
        
        keys_to_remove = []
        for key in list(self.role_cache.keys()):
            if key.startswith(f"{user_id}:"):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            self.role_cache.pop(key, None)
            
        keys_to_remove = []
        for key in list(self.access_cache.keys()):
            if key.startswith(f"{user_id}:"):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            self.access_cache.pop(key, None)
    
    def get_user_role_key(self, user: discord.Member) -> str:
        role_ids = sorted([r.id for r in user.roles if r.id != user.guild.default_role.id])
        if len(role_ids) > 10:
            import hashlib
            role_hash = hashlib.md5(':'.join(map(str, role_ids)).encode()).hexdigest()[:16]
            return f"{user.id}:h:{role_hash}"
        return f"{user.id}:{':'.join(map(str, role_ids))}"
    
    async def get_user_role_config(self, member: discord.Member, server: dict) -> Dict:
        if not server.get("role_based"):
            return {}
            
        best_config = {}
        highest_priority = -1
        
        server = await self.db.servers.find_one({"server_id": member.guild.id})
        if not server or not server.get("roles"):
            return {}
        
        for role in member.roles:
            role_config = server["roles"].get(str(role.id))
            if role_config and isinstance(role_config, dict):
                if role.position > highest_priority:
                    highest_priority = role.position
                    best_config = role_config
        
        return best_config
    
    async def get_user_cookie_access(self, member: discord.Member, server: dict, cookie_type: str) -> Dict:
        role_config = await self.get_user_role_config(member, server)
        
        if not role_config or "cookie_access" not in role_config:
            return {
                "enabled": True,
                "cost": server["cookies"][cookie_type]["cost"],
                "cooldown": server["cookies"][cookie_type]["cooldown"],
                "daily_limit": -1
            }
        
        cookie_access = role_config["cookie_access"].get(cookie_type, {})
        
        if not cookie_access.get("enabled", False):
            return {"enabled": False}
        
        return {
            "enabled": True,
            "cost": cookie_access.get("cost", server["cookies"][cookie_type]["cost"]),
            "cooldown": cookie_access.get("cooldown", server["cookies"][cookie_type]["cooldown"]),
            "daily_limit": cookie_access.get("daily_limit", -1)
        }
    
    async def check_daily_limit(self, user_id: int, cookie_type: str, limit: int) -> tuple[bool, int]:
        if limit == -1:
            return True, 0
            
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            return True, 0
            
        daily_claims = user.get("daily_claims", {}).get(cookie_type, {})
        
        last_claim = daily_claims.get("last_claim")
        if last_claim:
            if isinstance(last_claim, str):
                last_claim = datetime.fromisoformat(last_claim.replace('Z', '+00:00'))
            if last_claim.tzinfo is None:
                last_claim = last_claim.replace(tzinfo=timezone.utc)
                
            now = datetime.now(timezone.utc)
            if last_claim.date() < now.date():
                return True, 0
        
        current_count = daily_claims.get("count", 0)
        return current_count < limit, current_count
    
    async def update_daily_claim(self, user_id: int, cookie_type: str):
        now = datetime.now(timezone.utc)
        
        user = await self.db.users.find_one({"user_id": user_id})
        daily_claims = user.get("daily_claims", {}).get(cookie_type, {})
        
        last_claim = daily_claims.get("last_claim")
        if last_claim:
            if isinstance(last_claim, str):
                last_claim = datetime.fromisoformat(last_claim.replace('Z', '+00:00'))
            if last_claim.tzinfo is None:
                last_claim = last_claim.replace(tzinfo=timezone.utc)
                
            if last_claim.date() < now.date():
                count = 1
            else:
                count = daily_claims.get("count", 0) + 1
        else:
            count = 1
        
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    f"daily_claims.{cookie_type}": {
                        "count": count,
                        "last_claim": now
                    }
                }
            }
        )
    
    @tasks.loop(minutes=5)
    async def clear_role_cache(self):
        self.cooldown_cache.clear()
        self.role_cache.clear()
        self.access_cache.clear()
    
    @tasks.loop(time=time(hour=0, minute=0, tzinfo=timezone.utc))
    async def reset_daily_claims(self):
        try:
            print("🔄 Resetting daily cookie claims...")
            
            now = datetime.now(timezone.utc)
            reset_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            users_to_reset = await self.db.users.count_documents({
                "daily_claims": {"$exists": True, "$ne": {}}
            })
            
            if users_to_reset > 0:
                result = await self.db.users.update_many(
                    {"daily_claims": {"$exists": True, "$ne": {}}},
                    {
                        "$set": {"daily_claims": {}},
                        "$push": {
                            "claim_history": {
                                "date": reset_date,
                                "action": "daily_reset",
                                "timestamp": now
                            }
                        }
                    }
                )
                
                print(f"✅ Reset daily claims for {result.modified_count} users")
                
                await self.db.analytics.insert_one({
                    "type": "daily_reset",
                    "timestamp": now,
                    "users_reset": result.modified_count,
                    "reset_date": reset_date
                })
                
                config = await self.db.config.find_one({"_id": "bot_config"})
                if config and config.get("main_log_channel"):
                    channel = self.bot.get_channel(config["main_log_channel"])
                    if channel:
                        embed = discord.Embed(
                            title="🔄 Daily Claims Reset",
                            description=f"Reset daily cookie claims for **{result.modified_count}** users",
                            color=discord.Color.blue(),
                            timestamp=now
                        )
                        embed.add_field(name="Reset Time", value=f"<t:{int(now.timestamp())}:F>", inline=True)
                        embed.add_field(name="Next Reset", value=f"<t:{int((now + timedelta(days=1)).timestamp())}:R>", inline=True)
                        await channel.send(embed=embed)
            else:
                print("✅ No users needed daily claim reset")
                
        except Exception as e:
            print(f"❌ Error in daily claims reset: {e}")
            import traceback
            traceback.print_exc()
    
    @clear_role_cache.before_loop
    async def before_clear_role_cache(self):
        await self.bot.wait_until_ready()
        
    @reset_daily_claims.before_loop
    async def before_reset_daily_claims(self):
        await self.bot.wait_until_ready()
        
        now = datetime.now(timezone.utc)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (next_midnight - now).total_seconds()
        
        print(f"⏰ Daily reset task will start in {seconds_until_midnight/3600:.2f} hours (at midnight UTC)")
        
        await asyncio.sleep(seconds_until_midnight)
    
    async def cookie_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server = await self.db.servers.find_one({"server_id": interaction.guild_id})
        if not server:
            return []
        
        user_data = await self.get_or_create_user(interaction.user.id, str(interaction.user))
        
        choices = []
        for cookie_type, config in server.get("cookies", {}).items():
            if config.get("enabled", True) and cookie_type.lower().startswith(current.lower()):
                access = await self.get_user_cookie_access(interaction.user, server, cookie_type)
                if access.get("enabled", False):
                    cost = access.get("cost", config["cost"])
                    can_afford = user_data["points"] >= cost
                    
                    daily_limit = access.get("daily_limit", -1)
                    can_claim, claimed = await self.check_daily_limit(interaction.user.id, cookie_type, daily_limit)
                    
                    if not can_claim:
                        emoji = "🚫"
                        status = f"Daily limit reached ({claimed}/{daily_limit})"
                    else:
                        emoji = "✅" if can_afford else "❌"
                        status = f"{cost} points"
                        if daily_limit != -1:
                            status += f" ({claimed}/{daily_limit} today)"
                    
                    choices.append(app_commands.Choice(
                        name=f"{emoji} {cookie_type} - {status}",
                        value=cookie_type
                    ))
        
        return choices[:25]
    
    async def process_cookie_claim(self, interaction: discord.Interaction, cookie_type: str):
        try:
            if interaction.user.id in self.active_claims:
                await interaction.followup.send("⏳ Please wait for your current claim to complete!", ephemeral=True)
                del self.active_claims[interaction.user.id]
                return
            
            self.active_claims[interaction.user.id] = True
            
            progress_msg = await interaction.followup.send(
                embed=CookieProgressEmbed.create_claim_progress(0),
                ephemeral=True
            )
            
            server = await self.db.servers.find_one({"server_id": interaction.guild_id})
            user_data = await self.get_or_create_user(interaction.user.id, str(interaction.user))
            
            access = await self.get_user_cookie_access(interaction.user, server, cookie_type)
            
            if not access.get("enabled", False):
                embed = discord.Embed(
                    title="❌ Access Denied",
                    description=f"Your role doesn't have access to **{cookie_type}** cookies!",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 How to get access",
                    value="Get a higher role or ask an admin to configure your role's access.",
                    inline=False
                )
                await progress_msg.edit(embed=embed)
                del self.active_claims[interaction.user.id]
                return
            
            daily_limit = access.get("daily_limit", -1)
            can_claim, claimed_today = await self.check_daily_limit(interaction.user.id, cookie_type, daily_limit)
            
            if not can_claim:
                embed = discord.Embed(
                    title="🚫 Daily Limit Reached",
                    description=f"You've reached your daily limit for **{cookie_type}** cookies!",
                    color=discord.Color.red()
                )
                embed.add_field(name="Your Limit", value=f"{daily_limit} per day", inline=True)
                embed.add_field(name="Claimed Today", value=str(claimed_today), inline=True)
                embed.add_field(name="Reset Time", value="Midnight UTC", inline=True)
                embed.set_footer(text="Get a better role for higher limits!")
                
                await progress_msg.edit(embed=embed)
                del self.active_claims[interaction.user.id]
                return
            
            await asyncio.sleep(0.5)
            await progress_msg.edit(embed=CookieProgressEmbed.create_claim_progress(1))
            
            cooldown_hours = access.get("cooldown", server["cookies"][cookie_type]["cooldown"])
            
            if user_data.get("last_claim"):
                last_claim = user_data["last_claim"]
                
                # Handle both old format (datetime) and new format (dict)
                if isinstance(last_claim, datetime):
                    # Old format - convert to new format
                    claim_date = last_claim
                    claim_type = None
                elif isinstance(last_claim, dict):
                    # New format
                    claim_date = last_claim.get("date")
                    claim_type = last_claim.get("type")
                else:
                    # Unknown format - skip cooldown check
                    claim_date = None
                    claim_type = None
                
                # Check cooldown if we have valid data
                if claim_date and claim_type == cookie_type:
                    if claim_date.tzinfo is None:
                        claim_date = claim_date.replace(tzinfo=timezone.utc)
                    
                    time_passed = datetime.now(timezone.utc) - claim_date
                    if time_passed < timedelta(hours=cooldown_hours):
                        remaining = timedelta(hours=cooldown_hours) - time_passed
                        hours = int(remaining.total_seconds() // 3600)
                        minutes = int((remaining.total_seconds() % 3600) // 60)
                        
                        embed = discord.Embed(
                            title="⏰ Cooldown Active",
                            description=f"You need to wait before claiming another **{cookie_type}** cookie!",
                            color=discord.Color.red()
                        )
                        embed.add_field(name="Time Remaining", value=f"**{hours}h {minutes}m**", inline=False)
                        embed.add_field(name="Your Cooldown", value=f"**{cooldown_hours}** hours", inline=True)
                        embed.set_footer(text="Try a different cookie type or get a better role!")
                        
                        await progress_msg.edit(embed=embed)
                        del self.active_claims[interaction.user.id]
                        return
            
            await asyncio.sleep(0.5)
            await progress_msg.edit(embed=CookieProgressEmbed.create_claim_progress(2))
            
            cost = access.get("cost", server["cookies"][cookie_type]["cost"])
            
            if user_data["points"] < cost:
                embed = discord.Embed(
                    title="❌ Insufficient Points",
                    description=f"You need **{cost}** points to claim a **{cookie_type}** cookie!",
                    color=discord.Color.red()
                )
                embed.add_field(name="Your Balance", value=f"**{user_data['points']}** points", inline=True)
                embed.add_field(name="Required", value=f"**{cost}** points", inline=True)
                embed.add_field(name="Need More", value=f"**{cost - user_data['points']}** points", inline=True)
                embed.set_footer(text="Use /daily or invite friends to earn points!")
                
                await progress_msg.edit(embed=embed)
                del self.active_claims[interaction.user.id]
                return
            
            directory = server["cookies"][cookie_type]["directory"]
            if not os.path.exists(directory):
                embed = discord.Embed(
                    title="❌ Configuration Error",
                    description="Cookie directory not found! Please contact an administrator.",
                    color=discord.Color.red()
                )
                await progress_msg.edit(embed=embed)
                del self.active_claims[interaction.user.id]
                return
            
            files = [f for f in os.listdir(directory) if f.endswith('.txt')]
            if not files:
                embed = discord.Embed(
                    title="📦 Out of Stock",
                    description=f"No **{cookie_type}** cookies available!\nPlease try again later or choose a different type.",
                    color=discord.Color.red()
                )
                await progress_msg.edit(embed=embed)
                del self.active_claims[interaction.user.id]
                return
            
            selected_file = random.choice(files)
            file_path = os.path.join(directory, selected_file)
            
            try:
                await self.update_daily_claim(interaction.user.id, cookie_type)
                
                embed = discord.Embed(
                    title=f"🍪 {cookie_type.upper()} Cookie Delivery",
                    description=f"Your fresh **{cookie_type}** cookie is ready!",
                    color=discord.Color.green()
                )
                embed.add_field(name="📁 File", value=f"`{selected_file}`", inline=True)
                embed.add_field(name="💰 Cost", value=f"{cost} points", inline=True)
                embed.add_field(name="📊 Balance", value=f"{user_data['points'] - cost} points", inline=True)
                embed.add_field(name="⏰ Your Cooldown", value=f"{cooldown_hours} hours", inline=True)
                
                if daily_limit != -1:
                    embed.add_field(
                        name="📅 Daily Claims",
                        value=f"{claimed_today + 1}/{daily_limit}",
                        inline=True
                    )
                
                embed.add_field(
                    name="⚠️ Important",
                    value=f"Submit feedback in <#{server['channels']['feedback']}> within **15 minutes** or face a **30-day blacklist**!",
                    inline=False
                )
                
                role_config = await self.get_user_role_config(interaction.user, server)
                if role_config and role_config.get("name"):
                    embed.set_footer(text=f"Claimed with {role_config['name']} benefits! 🍪")
                else:
                    embed.set_footer(text="Enjoy your cookie! 🍪")
                
                dm_message = await interaction.user.send(
                    embed=embed,
                    file=discord.File(file_path)
                )
                
                config = await self.db.config.find_one({"_id": "bot_config"})
                feedback_deadline = datetime.now(timezone.utc) + timedelta(minutes=config.get("feedback_minutes", 15))
                
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {
                        "$set": {
                            "points": user_data["points"] - cost,
                            "last_claim": {
                                "date": datetime.now(timezone.utc),
                                "type": cookie_type,
                                "file": selected_file,
                                "server_id": interaction.guild_id,
                                "feedback_deadline": feedback_deadline,
                                "feedback_given": False,
                                "cost_paid": cost,
                                "cooldown_applied": cooldown_hours,
                                "role_benefits_applied": role_config.get("name") if role_config else None
                            }
                        },
                        "$inc": {
                            "total_spent": cost,
                            f"cookie_claims.{cookie_type}": 1,
                            "weekly_claims": 1,
                            "total_claims": 1
                        }
                    }
                )
                
                await self.update_statistics(cookie_type, interaction.user.id)
                
                analytics_cog = self.bot.get_cog("AnalyticsCog")
                if analytics_cog:
                    await analytics_cog.track_cookie_extraction(cookie_type, interaction.user.id, selected_file)
                    await analytics_cog.track_active_user(interaction.user.id, str(interaction.user))
                
                await asyncio.sleep(0.5)
                success_embed = discord.Embed(
                    title="✅ Cookie Delivered!",
                    description=f"Your **{cookie_type}** cookie has been sent to your DMs!",
                    color=discord.Color.green()
                )
                success_embed.add_field(name="💰 Transaction", value=f"-{cost} points", inline=True)
                success_embed.add_field(name="📊 New Balance", value=f"{user_data['points'] - cost} points", inline=True)
                success_embed.add_field(name="⏰ Cooldown", value=f"{cooldown_hours} hours", inline=True)
                
                if daily_limit != -1:
                    success_embed.add_field(
                        name="📅 Daily Status",
                        value=f"Claims today: {claimed_today + 1}/{daily_limit}",
                        inline=True
                    )
                
                success_embed.add_field(
                    name="📸 Feedback Required",
                    value=f"**Post a screenshot in <#{server['channels']['feedback']}> within 15 minutes!**\nDeadline: <t:{int(feedback_deadline.timestamp())}:R>",
                    inline=False
                )
                
                button1 = discord.ui.Button(
                    label="Quick Feedback (Optional)",
                    style=discord.ButtonStyle.success,
                    emoji="⭐"
                )
                
                button2 = discord.ui.Button(
                    label="Post Feedback Photo (Required)",
                    style=discord.ButtonStyle.primary,
                    emoji="📸"
                )
                
                async def feedback_callback(interaction: discord.Interaction):
                    feedback_cog = self.bot.get_cog("FeedbackCog")
                    if feedback_cog:
                        modal = feedback_cog.FeedbackModal(cookie_type)
                        await interaction.response.send_modal(modal)
                    else:
                        await interaction.response.send_message("❌ Feedback system not available!", ephemeral=True)
                
                async def photo_callback(interaction: discord.Interaction):
                    feedback_channel_id = server['channels']['feedback']
                    await interaction.response.send_message(
                        f"📸 Please post your screenshot in <#{feedback_channel_id}>\n"
                        f"**Required within 15 minutes or you'll be blacklisted!**",
                        ephemeral=True
                    )
                
                button1.callback = feedback_callback
                button2.callback = photo_callback
                
                view = discord.ui.View()
                view.add_item(button1)
                view.add_item(button2)
                
                await progress_msg.edit(embed=success_embed, view=view)
                
                await self.log_action(
                    interaction.guild_id,
                    f"🍪 {interaction.user.mention} claimed **{cookie_type}** cookie (`{selected_file}`) [-{cost} points] [CD: {cooldown_hours}h] [Role: {role_config.get('name') if role_config else 'Default'}]",
                    discord.Color.green()
                )
                
            except discord.Forbidden:
                error_embed = discord.Embed(
                    title="❌ DM Delivery Failed",
                    description="I couldn't send you a DM! Please check your privacy settings.",
                    color=discord.Color.red()
                )
                error_embed.add_field(
                    name="How to fix",
                    value="• Enable DMs from server members\n• Unblock the bot\n• Check privacy settings",
                    inline=False
                )
                await progress_msg.edit(embed=error_embed)
            
            del self.active_claims[interaction.user.id]
            
        except Exception as e:
            print(f"Error in process_cookie_claim: {traceback.format_exc()}")
            if interaction.user.id in self.active_claims:
                del self.active_claims[interaction.user.id]
            
            error_embed = discord.Embed(
                title="❌ Error",
                description="An unexpected error occurred. Please try again!",
                color=discord.Color.red()
            )
            try:
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except:
                pass
    
    @commands.hybrid_command(name="cookie", description="Claim a cookie with interactive menu")
    async def cookie(self, ctx):
        try:
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.response.defer(ephemeral=True)
            
            if not await self.check_maintenance(ctx):
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                embed = discord.Embed(
                    title="❌ Server Not Configured",
                    description="This server hasn't been set up yet!\nAsk an administrator to run the setup command.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
                
            if not server.get("enabled"):
                embed = discord.Embed(
                    title="❌ Bot Disabled",
                    description="The cookie system is currently disabled in this server.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            cookie_channel = server["channels"].get("cookie")
            if cookie_channel and ctx.channel.id != cookie_channel:
                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Please use <#{cookie_channel}> for cookie commands!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            blacklisted, expires = await self.check_blacklist(ctx.author.id)
            if blacklisted:
                embed = discord.Embed(
                    title="🚫 You're Blacklisted",
                    description=f"You cannot claim cookies until your blacklist expires.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Expires", value=f"<t:{int(expires.timestamp())}:R>", inline=False)
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.get_or_create_user(ctx.author.id, str(ctx.author))
            
            costs_dict = {}
            access_dict = {}
            daily_limits = {}
            
            role_config = await self.get_user_role_config(ctx.author, server)
            
            for cookie_type in server["cookies"].keys():
                access = await self.get_user_cookie_access(ctx.author, server, cookie_type)
                access_dict[cookie_type] = access.get("enabled", False)
                if access.get("enabled", False):
                    costs_dict[cookie_type] = access.get("cost", server["cookies"][cookie_type]["cost"])
                    daily_limits[cookie_type] = access.get("daily_limit", -1)
            
            embed = discord.Embed(
                title="🍪 Cookie Shop",
                description="Select a cookie type from the menu below!",
                color=discord.Color.blue()
            )
            embed.add_field(name="💰 Your Balance", value=f"{user_data['points']} points", inline=True)
            embed.add_field(name="🏆 Trust Score", value=f"{user_data.get('trust_score', 50)}", inline=True)
            embed.add_field(name="📊 Total Claims", value=f"{user_data.get('total_claims', 0)}", inline=True)
            
            if role_config:
                role_name = role_config.get("name", "Unknown")
                embed.add_field(
                    name="🎭 Your Role",
                    value=f"**{role_name}**",
                    inline=True
                )
                
                if role_config.get("daily_bonus", 0) > 0:
                    embed.add_field(
                        name="🎁 Daily Bonus",
                        value=f"+{role_config['daily_bonus']} points",
                        inline=True
                    )
                
                if role_config.get("trust_multiplier", 1.0) > 1.0:
                    embed.add_field(
                        name="✨ Trust Multiplier",
                        value=f"{role_config['trust_multiplier']}x",
                        inline=True
                    )
            
            available_cookies = sum(1 for enabled in access_dict.values() if enabled)
            embed.add_field(
                name="🍪 Available Cookies",
                value=f"{available_cookies} types",
                inline=False
            )
            
            favorite = user_data.get("statistics", {}).get("favorite_cookie")
            if favorite and access_dict.get(favorite, False):
                embed.add_field(name="⭐ Favorite", value=favorite.title(), inline=False)
            
            embed.set_footer(text="Select a cookie type below • Daily limits apply per cookie type")
            
            view = CookieView(self, ctx.author.id)
            select_menu = CookieSelectMenu(server, user_data, ctx.author, costs_dict, access_dict, daily_limits)
            view.add_item(select_menu)
            
            response = await ctx.send(embed=embed, view=view, ephemeral=True)
            view.response = response
            
        except Exception as e:
            print(f"Error in cookie command: {traceback.format_exc()}")
            error_embed = discord.Embed(
                title="❌ Error",
                description="An unexpected error occurred. Please try again!",
                color=discord.Color.red()
            )
            try:
                await ctx.send(embed=error_embed, ephemeral=True)
            except:
                pass
    
    @commands.hybrid_command(name="stock", description="Check cookie stock with beautiful display")
    @app_commands.describe(type="The type of cookie to check stock for (leave empty for all)")
    @app_commands.autocomplete(type=cookie_autocomplete)
    async def stock(self, ctx, type: str = None):
        try:
            interaction = ctx.interaction
            if interaction and not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 Cookie Stock Manager",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            role_config = await self.get_user_role_config(ctx.author, server)
            if role_config:
                embed.description = f"Viewing with **{role_config.get('name', 'Default')}** role benefits"
            
            total_stock = 0
            stock_data = []
            
            if type:
                type = type.lower()
                if type not in server["cookies"]:
                    await ctx.send("❌ Invalid cookie type!", ephemeral=True)
                    return
                    
                cookie_config = server["cookies"][type]
                directory = cookie_config["directory"]
                
                access = await self.get_user_cookie_access(ctx.author, server, type)
                
                if not access.get("enabled", False):
                    embed = discord.Embed(
                        title="❌ Access Denied",
                        description=f"Your role doesn't have access to **{type}** cookies!",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed, ephemeral=True)
                    return
                
                cost = access.get("cost", cookie_config["cost"])
                cooldown = access.get("cooldown", cookie_config["cooldown"])
                daily_limit = access.get("daily_limit", -1)
                
                can_claim, claimed_today = await self.check_daily_limit(ctx.author.id, type, daily_limit)
                
                if os.path.exists(directory):
                    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                    count = len(files)
                    
                    if count > 20:
                        status = "✅ Well Stocked"
                        color = discord.Color.green()
                    elif count > 10:
                        status = "🟨 Medium Stock"
                        color = discord.Color.gold()
                    elif count > 0:
                        status = "⚠️ Low Stock"
                        color = discord.Color.orange()
                    else:
                        status = "❌ Out of Stock"
                        color = discord.Color.red()
                    
                    embed.color = color
                    embed.add_field(
                        name=f"🍪 {type.title()} Cookie",
                        value=f"**Stock:** {count} files\n**Status:** {status}\n**Your Cost:** {cost} points\n**Your Cooldown:** {cooldown} hours",
                        inline=False
                    )
                    
                    if daily_limit != -1:
                        embed.add_field(
                            name="📅 Daily Limit",
                            value=f"**{claimed_today}/{daily_limit}** claimed today\n{'✅ Can claim' if can_claim else '❌ Limit reached'}",
                            inline=True
                        )
                    
                    progress = min(count / 50 * 100, 100)
                    bar_length = 20
                    filled = int(progress / 100 * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    embed.add_field(
                        name="Stock Level",
                        value=f"{bar} {progress:.0f}%",
                        inline=False
                    )
                else:
                    embed.add_field(name=type.title(), value="❌ Directory not found", inline=False)
            else:
                accessible_cookies = 0
                
                for cookie_type, cookie_config in server["cookies"].items():
                    if not cookie_config.get("enabled", True):
                        continue
                    
                    access = await self.get_user_cookie_access(ctx.author, server, cookie_type)
                    if not access.get("enabled", False):
                        continue
                        
                    accessible_cookies += 1
                    directory = cookie_config["directory"]
                    
                    if os.path.exists(directory):
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        count = len(files)
                        total_stock += count
                        
                        cost = access.get("cost", cookie_config["cost"])
                        daily_limit = access.get("daily_limit", -1)
                        can_claim, claimed_today = await self.check_daily_limit(ctx.author.id, cookie_type, daily_limit)
                        
                        if count > 20:
                            emoji = "🟢"
                        elif count > 10:
                            emoji = "🟡"
                        elif count > 0:
                            emoji = "🟠"
                        else:
                            emoji = "🔴"
                        
                        if not can_claim:
                            emoji = "🚫"
                        
                        stock_data.append((cookie_type, count, emoji, cost, daily_limit, claimed_today))
                
                stock_data.sort(key=lambda x: x[1], reverse=True)
                
                for cookie_type, count, emoji, cost, limit, claimed in stock_data[:10]:
                    field_value = f"**{count}** files\n{cost} points"
                    if limit != -1:
                        field_value += f"\n{claimed}/{limit} today"
                    
                    embed.add_field(
                        name=f"{emoji} {cookie_type.title()}",
                        value=field_value,
                        inline=True
                    )
                
                if accessible_cookies == 0:
                    embed.add_field(
                        name="❌ No Access",
                        value="Your role doesn't have access to any cookies!",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📊 Summary",
                        value=f"**{accessible_cookies}** accessible types\n**{total_stock}** total files",
                        inline=False
                    )
                
                if total_stock > 100:
                    health = "🟢 Excellent"
                elif total_stock > 50:
                    health = "🟡 Good"
                elif total_stock > 20:
                    health = "🟠 Fair"
                else:
                    health = "🔴 Critical"
                
                embed.set_footer(text=f"Total Stock: {total_stock} files | Health: {health}")
            
            if interaction and interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in stock command: {e}")
            try:
                await ctx.send("❌ An error occurred!", ephemeral=True)
            except:
                pass
    
    @commands.hybrid_command(name="refresh", description="Refresh your role benefits")
    async def refresh(self, ctx):
        try:
            self.clear_user_cache(ctx.author.id)
            
            embed = discord.Embed(
                title="🔄 Benefits Refreshed!",
                description="Your role benefits have been refreshed.",
                color=discord.Color.green()
            )
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if server and server.get("role_based"):
                role_config = await self.get_user_role_config(ctx.author, server)
                
                if role_config:
                    embed.add_field(
                        name="🎭 Active Role",
                        value=f"**{role_config.get('name', 'Unknown')}**",
                        inline=False
                    )
                    
                    benefits = []
                    if role_config.get("daily_bonus", 0) > 0:
                        benefits.append(f"• Daily Bonus: +{role_config['daily_bonus']} points")
                    if role_config.get("trust_multiplier", 1.0) > 1.0:
                        benefits.append(f"• Trust Multiplier: {role_config['trust_multiplier']}x")
                    
                    accessible = 0
                    if "cookie_access" in role_config:
                        for cookie, access in role_config["cookie_access"].items():
                            if access.get("enabled", False):
                                accessible += 1
                    
                    benefits.append(f"• Accessible Cookies: {accessible} types")
                    
                    if benefits:
                        embed.add_field(
                            name="✨ Your Benefits",
                            value="\n".join(benefits),
                            inline=False
                        )
                else:
                    embed.add_field(
                        name="ℹ️ No Role Benefits",
                        value="You don't have any roles with cookie benefits.",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="ℹ️ Role System",
                    value="Role-based benefits are not enabled in this server.",
                    inline=False
                )
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await ctx.send("❌ Error refreshing benefits!", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            self.clear_user_cache(after.id)
            
            added_roles = set(after.roles) - set(before.roles)
            removed_roles = set(before.roles) - set(after.roles)
            
            if added_roles or removed_roles:
                server = await self.db.servers.find_one({"server_id": after.guild.id})
                if server and server.get("role_based"):
                    for role in added_roles:
                        if str(role.id) in server.get("roles", {}):
                            role_config = server["roles"][str(role.id)]
                            if isinstance(role_config, dict):
                                await self.log_action(
                                    after.guild.id,
                                    f"🎭 {after.mention} received role {role.mention} with **{role_config.get('name', 'Unknown')}** cookie benefits",
                                    discord.Color.green()
                                )
                    
                    for role in removed_roles:
                        if str(role.id) in server.get("roles", {}):
                            role_config = server["roles"][str(role.id)]
                            if isinstance(role_config, dict):
                                await self.log_action(
                                    after.guild.id,
                                    f"🎭 {after.mention} lost role {role.mention} with **{role_config.get('name', 'Unknown')}** cookie benefits",
                                    discord.Color.orange()
                                )

    @commands.hybrid_command(name="fixclaims", description="Fix last_claim data (Owner only)")
    async def fixclaims(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ Owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        fixed = 0
        async for user in self.db.users.find({"last_claim": {"$exists": True}}):
            last_claim = user.get("last_claim")
            
            # If last_claim is a datetime, convert to dict format
            if isinstance(last_claim, datetime):
                await self.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {
                        "$set": {
                            "last_claim": {
                                "date": last_claim,
                                "type": "unknown",
                                "feedback_given": False
                            }
                        }
                    }
                )
                fixed += 1
        
        await ctx.send(f"✅ Fixed {fixed} users' claim data!")

    async def is_owner(self, user_id: int) -> bool:
        """Check if a user is the bot owner"""
        config = await self.db.config.find_one({"_id": "bot_config"})
        return config and config.get("owner_id") == user_id

async def setup(bot):
    await bot.add_cog(CookieCog(bot))