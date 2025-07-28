import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import random
from datetime import datetime, timedelta, timezone
import traceback
from typing import List
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
    def __init__(self, server_data, user_data, member, costs_dict):
        self.server_data = server_data
        self.user_data = user_data
        self.member = member
        self.costs_dict = costs_dict
        
        options = []
        for cookie_type, config in server_data["cookies"].items():
            if config.get("enabled", True):
                cost = self.costs_dict.get(cookie_type, config["cost"])
                can_afford = user_data["points"] >= cost
                emoji = "🟢" if can_afford else "🔴"
                
                directory = config["directory"]
                stock = 0
                if os.path.exists(directory):
                    stock = len([f for f in os.listdir(directory) if f.endswith('.txt')])
                
                options.append(
                    discord.SelectOption(
                        label=f"{cookie_type.title()}",
                        value=cookie_type,
                        description=f"{emoji} {cost} points | Stock: {stock}",
                        emoji="🍪"
                    )
                )
        
        super().__init__(
            placeholder="🍪 Select a cookie type...",
            options=options[:25],
            custom_id="cookie_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
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
        self.active_claims = {}
        self.cooldown_cache = {}
        self.role_cache = {}
        
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
        config = await self.db.config.find_one({"_id": "bot_config"})
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
    
    def get_user_role_key(self, user: discord.Member) -> str:
        role_ids = sorted([r.id for r in user.roles if r.id != user.guild.default_role.id])
        return f"{user.id}:{':'.join(map(str, role_ids))}"
    
    async def get_user_cooldown(self, user: discord.Member, server: dict, cookie_type: str, force_refresh: bool = False) -> int:
        role_key = self.get_user_role_key(user)
        cache_key = f"{role_key}:{cookie_type}:cooldown"
        
        if not force_refresh and cache_key in self.cooldown_cache:
            cached_time, value = self.cooldown_cache[cache_key]
            if datetime.now() - cached_time < timedelta(minutes=5):
                return value
            
        if not server.get("role_based"):
            cooldown = server["cookies"][cookie_type]["cooldown"]
        else:
            min_cooldown = server["cookies"][cookie_type]["cooldown"]
            
            server = await self.db.servers.find_one({"server_id": user.guild.id})
            if server and server.get("roles"):
                for role in user.roles:
                    role_config = server["roles"].get(str(role.id))
                    if role_config:
                        if "all" in role_config["access"] or cookie_type in role_config["access"]:
                            min_cooldown = min(min_cooldown, role_config["cooldown"])
            
            cooldown = min_cooldown
        
        self.cooldown_cache[cache_key] = (datetime.now(), cooldown)
        return cooldown
    
    async def get_user_cost(self, user: discord.Member, server: dict, cookie_type: str, force_refresh: bool = False) -> int:
        role_key = self.get_user_role_key(user)
        cache_key = f"{role_key}:{cookie_type}:cost"
        
        if not force_refresh and cache_key in self.role_cache:
            cached_time, value = self.role_cache[cache_key]
            if datetime.now() - cached_time < timedelta(minutes=5):
                return value
            
        if not server.get("role_based"):
            cost = server["cookies"][cookie_type]["cost"]
        else:
            min_cost = server["cookies"][cookie_type]["cost"]
            
            server = await self.db.servers.find_one({"server_id": user.guild.id})
            if server and server.get("roles"):
                for role in user.roles:
                    role_config = server["roles"].get(str(role.id))
                    if role_config:
                        if "all" in role_config["access"] or cookie_type in role_config["access"]:
                            if role_config["cost"] != "default":
                                min_cost = min(min_cost, role_config["cost"])
            
            cost = min_cost
        
        self.role_cache[cache_key] = (datetime.now(), cost)
        return cost
    
    @tasks.loop(minutes=5)
    async def clear_role_cache(self):
        self.cooldown_cache.clear()
        self.role_cache.clear()
    
    @clear_role_cache.before_loop
    async def before_clear_role_cache(self):
        await self.bot.wait_until_ready()
    
    async def cookie_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server = await self.db.servers.find_one({"server_id": interaction.guild_id})
        if not server:
            return []
        
        user_data = await self.get_or_create_user(interaction.user.id, str(interaction.user))
        
        choices = []
        for cookie_type, config in server.get("cookies", {}).items():
            if config.get("enabled", True) and cookie_type.lower().startswith(current.lower()):
                cost = await self.get_user_cost(interaction.user, server, cookie_type)
                can_afford = user_data["points"] >= cost
                emoji = "✅" if can_afford else "❌"
                choices.append(app_commands.Choice(
                    name=f"{emoji} {cookie_type} ({cost} points)",
                    value=cookie_type
                ))
        
        return choices[:25]
    
    async def process_cookie_claim(self, interaction: discord.Interaction, cookie_type: str):
        try:
            if interaction.user.id in self.active_claims:
                await interaction.followup.send("⏳ Please wait for your current claim to complete!", ephemeral=True)
                return
                
            self.active_claims[interaction.user.id] = True
            
            progress_msg = await interaction.followup.send(
                embed=CookieProgressEmbed.create_claim_progress(0),
                ephemeral=True
            )
            
            server = await self.db.servers.find_one({"server_id": interaction.guild_id})
            user_data = await self.get_or_create_user(interaction.user.id, str(interaction.user))
            
            await asyncio.sleep(0.5)
            await progress_msg.edit(embed=CookieProgressEmbed.create_claim_progress(1))
            
            cookie_config = server["cookies"][cookie_type]
            cooldown_hours = await self.get_user_cooldown(interaction.user, server, cookie_type)
            
            if user_data.get("last_claim"):
                last_claim = user_data["last_claim"]
                if last_claim.get("type") == cookie_type:
                    claim_date = last_claim["date"]
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
            
            cost = await self.get_user_cost(interaction.user, server, cookie_type)
            
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
            
            directory = cookie_config["directory"]
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
                embed = discord.Embed(
                    title=f"🍪 {cookie_type.upper()} Cookie Delivery",
                    description=f"Your fresh **{cookie_type}** cookie is ready!",
                    color=discord.Color.green()
                )
                embed.add_field(name="📁 File", value=f"`{selected_file}`", inline=True)
                embed.add_field(name="💰 Cost", value=f"{cost} points", inline=True)
                embed.add_field(name="📊 Balance", value=f"{user_data['points'] - cost} points", inline=True)
                embed.add_field(name="⏰ Your Cooldown", value=f"{cooldown_hours} hours", inline=True)
                embed.add_field(
                    name="⚠️ Important",
                    value=f"Submit feedback in <#{server['channels']['feedback']}> within **15 minutes** or face a **30-day blacklist**!",
                    inline=False
                )
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
                                "cooldown_applied": cooldown_hours
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
                    f"🍪 {interaction.user.mention} claimed **{cookie_type}** cookie (`{selected_file}`) [-{cost} points] [Cooldown: {cooldown_hours}h]",
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
            # Properly handle both slash and text commands
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
            for cookie_type in server["cookies"].keys():
                costs_dict[cookie_type] = await self.get_user_cost(ctx.author, server, cookie_type, force_refresh=True)
            
            embed = discord.Embed(
                title="🍪 Cookie Shop",
                description="Select a cookie type from the menu below!",
                color=discord.Color.blue()
            )
            embed.add_field(name="💰 Your Balance", value=f"{user_data['points']} points", inline=True)
            embed.add_field(name="🏆 Trust Score", value=f"{user_data.get('trust_score', 50)}", inline=True)
            embed.add_field(name="📊 Total Claims", value=f"{user_data.get('total_claims', 0)}", inline=True)
            
            if server.get("role_based"):
                role_benefits = []
                for role in ctx.author.roles:
                    role_config = server["roles"].get(str(role.id))
                    if role_config:
                        role_benefits.append(f"• **{role.name}**: {role_config['cooldown']}h cooldown")
                
                if role_benefits:
                    embed.add_field(
                        name="🎭 Your Role Benefits",
                        value="\n".join(role_benefits[:3]),
                        inline=False
                    )
            
            favorite = user_data.get("statistics", {}).get("favorite_cookie")
            if favorite:
                embed.add_field(name="⭐ Favorite", value=favorite.title(), inline=False)
            
            embed.set_footer(text="Select a cookie type below")
            
            view = CookieView(self, ctx.author.id)
            select_menu = CookieSelectMenu(server, user_data, ctx.author, costs_dict)
            view.add_item(select_menu)
            
            # Properly send message for both command types
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
            
            total_stock = 0
            stock_data = []
            
            if type:
                type = type.lower()
                if type not in server["cookies"]:
                    await ctx.send("❌ Invalid cookie type!", ephemeral=True)
                    return
                    
                cookie_config = server["cookies"][type]
                directory = cookie_config["directory"]
                
                cost = await self.get_user_cost(ctx.author, server, type)
                cooldown = await self.get_user_cooldown(ctx.author, server, type)
                
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
                for cookie_type, cookie_config in server["cookies"].items():
                    if not cookie_config.get("enabled", True):
                        continue
                        
                    directory = cookie_config["directory"]
                    if os.path.exists(directory):
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        count = len(files)
                        total_stock += count
                        
                        cost = await self.get_user_cost(ctx.author, server, cookie_type)
                        
                        if count > 20:
                            emoji = "🟢"
                        elif count > 10:
                            emoji = "🟡"
                        elif count > 0:
                            emoji = "🟠"
                        else:
                            emoji = "🔴"
                        
                        stock_data.append((cookie_type, count, emoji, cost))
                
                stock_data.sort(key=lambda x: x[1], reverse=True)
                
                for cookie_type, count, emoji, cost in stock_data[:10]:
                    embed.add_field(
                        name=f"{emoji} {cookie_type.title()}",
                        value=f"**{count}** files\n{cost} points",
                        inline=True
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
                role_benefits = []
                for role in ctx.author.roles:
                    role_config = server["roles"].get(str(role.id))
                    if role_config:
                        role_benefits.append(f"• **{role.name}**: {role_config['cooldown']}h cooldown, {role_config['cost']} cost")
                
                if role_benefits:
                    embed.add_field(
                        name="🎭 Your Active Benefits",
                        value="\n".join(role_benefits[:5]),
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
                if server:
                    for role in added_roles:
                        if str(role.id) in server.get("roles", {}):
                            await self.log_action(
                                after.guild.id,
                                f"🎭 {after.mention} received role {role.mention} with cookie benefits",
                                discord.Color.green()
                            )
                    for role in removed_roles:
                        if str(role.id) in server.get("roles", {}):
                            await self.log_action(
                                after.guild.id,
                                f"🎭 {after.mention} lost role {role.mention} with cookie benefits",
                                discord.Color.orange()
                            )

async def setup(bot):
    await bot.add_cog(CookieCog(bot))