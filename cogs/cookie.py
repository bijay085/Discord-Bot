# cogs/cookie.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
from datetime import datetime, timedelta, timezone
import traceback
from typing import List

class CookieCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_feedback_deadlines.start()
        
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
                "blacklist_expires": None
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
            expires = user["blacklist_expires"]
            # Ensure expires is timezone-aware
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
    
    async def cookie_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server = await self.db.servers.find_one({"server_id": interaction.guild_id})
        if not server:
            return []
        
        choices = []
        for cookie_type, config in server.get("cookies", {}).items():
            if config.get("enabled", True) and cookie_type.lower().startswith(current.lower()):
                cost = config.get("cost", 0)
                choices.append(app_commands.Choice(name=f"{cookie_type} ({cost} points)", value=cookie_type))
        
        return choices[:25]
    
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
                    deadline = last_claim["feedback_deadline"]
                    # Ensure deadline is timezone-aware
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    
                    if now > deadline:
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
                                f"🚫 <@{user['user_id']}> blacklisted for not providing feedback",
                                discord.Color.red()
                            )
        except Exception as e:
            print(f"Error in feedback check: {e}")

    @commands.hybrid_command(name="cookie", description="Claim a cookie")
    @app_commands.describe(type="The type of cookie you want to claim")
    @app_commands.autocomplete(type=cookie_autocomplete)
    async def cookie(self, ctx, type: str):
        try:
            if not await self.check_maintenance(ctx):
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
                    claim_date = last_claim["date"]
                    # Ensure both datetimes are timezone-aware
                    if claim_date.tzinfo is None:
                        claim_date = claim_date.replace(tzinfo=timezone.utc)
                    
                    time_passed = datetime.now(timezone.utc) - claim_date
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
            
            # Send initial response
            initial_msg = await ctx.send(f"✅ Processing your {type} cookie request...", ephemeral=True)
            
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
                            }
                        },
                        "$inc": {
                            "total_spent": cost,
                            f"cookie_claims.{type}": 1,
                            "weekly_claims": 1,
                            "total_claims": 1
                        }
                    }
                )
                
                await self.update_statistics(type, ctx.author.id)
                
                # Track analytics
                analytics_cog = self.bot.get_cog("AnalyticsCog")
                if analytics_cog:
                    await analytics_cog.track_cookie_extraction(type, ctx.author.id, selected_file)
                    await analytics_cog.track_active_user(ctx.author.id, str(ctx.author))
                
                # Edit the initial message
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.edit_original_response(
                        content=f"✅ **{type}** cookie sent to your DMs!\n"
                        f"💰 -{cost} points | Balance: **{user_data['points'] - cost}** points\n"
                        f"⏰ Submit feedback in <#{server['channels']['feedback']}> within **15 minutes**!"
                    )
                else:
                    await initial_msg.edit(
                        content=f"✅ **{type}** cookie sent to your DMs!\n"
                        f"💰 -{cost} points | Balance: **{user_data['points'] - cost}** points\n"
                        f"⏰ Submit feedback in <#{server['channels']['feedback']}> within **15 minutes**!"
                    )
                
                await self.log_action(
                    ctx.guild.id,
                    f"🍪 {ctx.author.mention} claimed **{type}** cookie (`{selected_file}`) [-{cost} points]",
                    discord.Color.green()
                )
                
            except discord.Forbidden:
                error_msg = "❌ **I can't send you a DM!**\n\n" \
                           "Please check:\n" \
                           "• Enable DMs from server members\n" \
                           "• Make sure you haven't blocked the bot\n" \
                           "• Check your privacy settings"
                
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.edit_original_response(content=error_msg)
                else:
                    await initial_msg.edit(content=error_msg)
                return
                
        except Exception as e:
            print(f"Error in cookie command: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred! Please try again or contact support.", ephemeral=True)

    @commands.hybrid_command(name="stock", description="Check cookie stock")
    @app_commands.describe(type="The type of cookie to check stock for (leave empty for all)")
    @app_commands.autocomplete(type=cookie_autocomplete)
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
            
            deadline = last_claim["feedback_deadline"]
            # Ensure deadline is timezone-aware
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            
            if datetime.now(timezone.utc) > deadline:
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