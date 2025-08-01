# cogs/admin.py
# Location: cogs/admin.py
# Description: Updated admin module with enhanced role management and new DB structure

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
import traceback
from typing import Optional

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
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
                "invited_users": [],
                "pending_invites": 0,
                "verified_invites": 0,
                "fake_invites": 0,
                "last_claim": None,
                "cookie_claims": {},
                "daily_claims": {},
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
                    "favorite_cookie": None,
                    "divine_gambles": 0,
                    "divine_wins": 0,
                    "divine_losses": 0,
                    "rob_wins": 0,
                    "rob_losses": 0,
                    "rob_winnings": 0,
                    "rob_losses_amount": 0,
                    "times_robbed": 0,
                    "amount_stolen_from": 0,
                    "slots_played": 0,
                    "slots_won": 0,
                    "slots_lost": 0,
                    "slots_profit": 0,
                    "slots_biggest_win": 0,
                    "slots_current_streak": 0,
                    "slots_best_streak": 0
                },
                "game_stats": {
                    "slots": {"played": 0, "won": 0, "profit": 0},
                    "bet": {"played": 0, "won": 0, "profit": 0},
                    "rob": {"attempts": 0, "successes": 0, "profit": 0},
                    "gamble": {"attempts": 0, "wins": 0}
                }
            }
            await self.db.users.insert_one(user)
        return user

    @commands.hybrid_command(name="givepoints", description="Give or remove points from a user")
    @app_commands.describe(
        user="The user to give points to",
        points="Amount of points (negative to remove)"
    )
    async def givepoints(self, ctx, user: discord.Member, points: int):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Your ID: {ctx.author.id}")
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.get_or_create_user(user.id, str(user))
            current_points = user_data.get("points", 0)
            
            if points > 0:
                await self.db.users.update_one(
                    {"user_id": user.id},
                    {
                        "$inc": {
                            "points": points,
                            "total_earned": points
                        },
                        "$set": {"last_active": datetime.now(timezone.utc)}
                    }
                )
                action = "Added"
                emoji = "➕"
                color = discord.Color.green()
            else:
                await self.db.users.update_one(
                    {"user_id": user.id},
                    {
                        "$inc": {"points": points},
                        "$set": {"last_active": datetime.now(timezone.utc)}
                    }
                )
                action = "Removed"
                emoji = "➖"
                color = discord.Color.red()
            
            new_balance = current_points + points
            
            embed = discord.Embed(
                title=f"{emoji} Points {action}!",
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Amount", value=f"**{abs(points):,}** points", inline=True)
            embed.add_field(name="Action", value=action, inline=True)
            embed.add_field(name="Previous Balance", value=f"**{current_points:,}** points", inline=True)
            embed.add_field(name="New Balance", value=f"**{new_balance:,}** points", inline=True)
            embed.add_field(name="Change", value=f"{'+' if points > 0 else ''}{points:,}", inline=True)
            embed.set_footer(text=f"Executed by {ctx.author}")
            embed.set_thumbnail(url=user.display_avatar.url)
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"💰 {ctx.author.mention} {action.lower()} **{abs(points):,}** points {'to' if points > 0 else 'from'} {user.mention} [New balance: {new_balance:,}]",
                color
            )
        except Exception as e:
            print(f"Error in givepoints: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="checkpoints", description="Check a user's points and statistics")
    @app_commands.describe(user="The user to check points for")
    async def checkpoints(self, ctx, user: discord.Member):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": user.id})
            if not user_data:
                embed = discord.Embed(
                    title="❌ User Not Found",
                    description=f"{user.mention} has not used the bot yet!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            role_info = "Default"
            
            if server and server.get("role_based"):
                best_role = None
                highest_position = -1
                
                for role in user.roles:
                    role_config = server.get("roles", {}).get(str(role.id))
                    if role_config and isinstance(role_config, dict):
                        if role.position > highest_position:
                            highest_position = role.position
                            best_role = role_config
                
                if best_role:
                    role_info = f"{best_role.get('name', 'Unknown')} (×{best_role.get('trust_multiplier', 1.0)} trust)"
            
            embed = discord.Embed(
                title=f"💰 Points Analysis: {user.display_name}",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            embed.add_field(name="💵 Current Points", value=f"**{user_data.get('points', 0):,}**", inline=True)
            embed.add_field(name="📈 Total Earned", value=f"**{user_data.get('total_earned', 0):,}**", inline=True)
            embed.add_field(name="📉 Total Spent", value=f"**{user_data.get('total_spent', 0):,}**", inline=True)
            
            net_profit = user_data.get('total_earned', 0) - user_data.get('total_spent', 0)
            embed.add_field(name="💹 Net Profit", value=f"**{net_profit:,}**", inline=True)
            embed.add_field(name="🏆 Trust Score", value=f"**{user_data.get('trust_score', 50)}/100**", inline=True)
            embed.add_field(name="🍪 Total Claims", value=f"**{user_data.get('total_claims', 0):,}**", inline=True)
            
            embed.add_field(name="🎭 Active Role", value=role_info, inline=False)
            
            # Show game stats
            game_stats = user_data.get("game_stats", {})
            game_text = []
            if game_stats.get("slots", {}).get("played", 0) > 0:
                game_text.append(f"Slots: {game_stats['slots']['won']}/{game_stats['slots']['played']} wins")
            if game_stats.get("rob", {}).get("attempts", 0) > 0:
                game_text.append(f"Rob: {game_stats['rob']['successes']}/{game_stats['rob']['attempts']} success")
            if game_text:
                embed.add_field(name="🎮 Game Stats", value="\n".join(game_text), inline=False)
            
            if user_data.get('blacklisted'):
                expires = user_data.get('blacklist_expires')
                if expires:
                    embed.add_field(
                        name="⚠️ Status",
                        value=f"🚫 **BLACKLISTED**\nExpires: <t:{int(expires.timestamp())}:R>",
                        inline=False
                    )
                else:
                    embed.add_field(name="⚠️ Status", value="🚫 **PERMANENTLY BLACKLISTED**", inline=False)
            else:
                embed.add_field(name="✅ Status", value="Active", inline=False)
            
            embed.set_footer(text=f"User ID: {user.id}")
            
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"Error in checkpoints: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="maintenance", description="Toggle maintenance mode")
    @app_commands.describe(mode="Enable or disable maintenance mode")
    async def maintenance(self, ctx, mode: bool):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            await self.db.config.update_one(
                {"_id": "bot_config"},
                {
                    "$set": {
                        "maintenance_mode": mode,
                        "maintenance_started": datetime.now(timezone.utc) if mode else None
                    }
                }
            )
            
            if mode:
                embed = discord.Embed(
                    title="🔧 Maintenance Mode Enabled",
                    description="The bot is now in maintenance mode.\nOnly the owner can use commands.",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Status", value="🟠 Maintenance", inline=True)
                embed.add_field(name="Access", value="🔒 Owner Only", inline=True)
            else:
                embed = discord.Embed(
                    title="✅ Maintenance Mode Disabled",
                    description="The bot is now fully operational!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Status", value="🟢 Operational", inline=True)
                embed.add_field(name="Access", value="🔓 All Users", inline=True)
            
            embed.set_footer(text=f"Changed by {ctx.author}")
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"🔧 {ctx.author.mention} {'enabled' if mode else 'disabled'} maintenance mode",
                discord.Color.orange() if mode else discord.Color.green()
            )
        except Exception as e:
            print(f"Error in maintenance: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="blacklist", description="Blacklist a user from using the bot")
    @app_commands.describe(
        user="The user to blacklist",
        days="Number of days to blacklist (0 for permanent)"
    )
    async def blacklist(self, ctx, user: discord.Member, days: int = 30):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            if user.id == ctx.author.id:
                await ctx.send("❌ You cannot blacklist yourself!", ephemeral=True)
                return
            
            if user.id == self.bot.user.id:
                await ctx.send("❌ I cannot blacklist myself!", ephemeral=True)
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if server:
                settings = server.get("settings", {})
                max_blacklist_days = settings.get("max_blacklist_days", 365)
                if days > max_blacklist_days:
                    days = max_blacklist_days
            
            if days > 0:
                expire_date = datetime.now(timezone.utc) + timedelta(days=days)
                duration_text = f"**{days}** days"
            else:
                expire_date = None
                duration_text = "**PERMANENTLY**"
            
            await self.db.users.update_one(
                {"user_id": user.id},
                {
                    "$set": {
                        "blacklisted": True,
                        "blacklist_expires": expire_date,
                        "blacklist_reason": "Admin action",
                        "blacklisted_by": ctx.author.id,
                        "blacklisted_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
            
            embed = discord.Embed(
                title="🚫 User Blacklisted",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Duration", value=duration_text, inline=True)
            
            if expire_date:
                embed.add_field(name="Expires", value=f"<t:{int(expire_date.timestamp())}:F>", inline=True)
                embed.add_field(name="Countdown", value=f"<t:{int(expire_date.timestamp())}:R>", inline=True)
            
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Blacklisted by {ctx.author}")
            
            await ctx.send(embed=embed)
            
            try:
                dm_embed = discord.Embed(
                    title="⚠️ You've Been Blacklisted",
                    description=f"You have been blacklisted from using Cookie Bot in **{ctx.guild.name}**",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="Duration", value=duration_text, inline=False)
                if expire_date:
                    dm_embed.add_field(name="Expires", value=f"<t:{int(expire_date.timestamp())}:R>", inline=False)
                dm_embed.add_field(name="Reason", value="Contact server administrators for more information", inline=False)
                
                await user.send(embed=dm_embed)
            except:
                pass
            
            # Check if user has blacklist role
            if server and server.get("roles"):
                for role_id, role_config in server["roles"].items():
                    if isinstance(role_config, dict) and role_config.get("name") == "blacklist":
                        blacklist_role = ctx.guild.get_role(int(role_id))
                        if blacklist_role and blacklist_role not in user.roles:
                            await user.add_roles(blacklist_role)
                        break
            
            await self.log_action(
                ctx.guild.id,
                f"🚫 {ctx.author.mention} blacklisted {user.mention} for {duration_text}",
                discord.Color.red()
            )
        except Exception as e:
            print(f"Error in blacklist: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="unblacklist", description="Remove a user from the blacklist")
    @app_commands.describe(user="The user to unblacklist")
    async def unblacklist(self, ctx, user: discord.Member):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": user.id})
            if not user_data or not user_data.get("blacklisted"):
                embed = discord.Embed(
                    title="❌ Not Blacklisted",
                    description=f"{user.mention} is not currently blacklisted!",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            await self.db.users.update_one(
                {"user_id": user.id},
                {
                    "$set": {
                        "blacklisted": False,
                        "blacklist_expires": None,
                        "last_claim.feedback_given": True
                    },
                    "$unset": {
                        "blacklist_reason": "",
                        "blacklisted_by": "",
                        "blacklisted_at": ""
                    }
                }
            )
            
            embed = discord.Embed(
                title="✅ User Unblacklisted",
                description=f"{user.mention} has been removed from the blacklist!",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Status", value="✅ Active", inline=True)
            embed.add_field(name="Can Use Bot", value="Yes", inline=True)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Unblacklisted by {ctx.author}")
            
            await ctx.send(embed=embed)
            
            # Remove blacklist role if exists
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if server and server.get("roles"):
                for role_id, role_config in server["roles"].items():
                    if isinstance(role_config, dict) and role_config.get("name") == "blacklist":
                        blacklist_role = ctx.guild.get_role(int(role_id))
                        if blacklist_role and blacklist_role in user.roles:
                            await user.remove_roles(blacklist_role)
                        break
            
            try:
                dm_embed = discord.Embed(
                    title="✅ Blacklist Removed",
                    description=f"Your blacklist has been removed in **{ctx.guild.name}**!\nYou can now use the bot again.",
                    color=discord.Color.green()
                )
                await user.send(embed=dm_embed)
            except:
                pass
            
            await self.log_action(
                ctx.guild.id,
                f"✅ {ctx.author.mention} unblacklisted {user.mention}",
                discord.Color.green()
            )
        except Exception as e:
            print(f"Error in unblacklist: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="stats", description="View comprehensive bot statistics")
    async def stats(self, ctx):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            await ctx.defer()
            
            # Database stats
            total_users = await self.db.users.count_documents({})
            blacklisted_users = await self.db.users.count_documents({"blacklisted": True})
            total_servers = await self.db.servers.count_documents({})
            active_servers = await self.db.servers.count_documents({"enabled": True})
            setup_complete_servers = await self.db.servers.count_documents({"setup_complete": True})
            
            # Points statistics
            points_pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_points": {"$sum": "$points"},
                        "total_earned": {"$sum": "$total_earned"},
                        "total_spent": {"$sum": "$total_spent"},
                        "avg_points": {"$avg": "$points"},
                        "avg_trust": {"$avg": "$trust_score"}
                    }
                }
            ]
            points_stats = await self.db.users.aggregate(points_pipeline).to_list(1)
            points_data = points_stats[0] if points_stats else {}
            
            # Global statistics
            stats = await self.db.statistics.find_one({"_id": "global_stats"})
            if not stats:
                stats = {"all_time_claims": 0, "total_claims": {}, "game_stats": {}}
            
            # Game statistics
            game_stats = stats.get("game_stats", {})
            
            # Create main embed
            embed = discord.Embed(
                title="📊 Comprehensive Bot Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # User Statistics
            embed.add_field(
                name="👥 User Statistics",
                value=f"Total Users: **{total_users:,}**\n"
                      f"Blacklisted: **{blacklisted_users}** ({blacklisted_users/max(total_users, 1)*100:.1f}%)\n"
                      f"Active Users: **{total_users - blacklisted_users:,}**",
                inline=True
            )
            
            # Server Statistics
            embed.add_field(
                name="🏢 Server Statistics",
                value=f"Total Servers: **{total_servers}**\n"
                      f"Active Servers: **{active_servers}**\n"
                      f"Setup Complete: **{setup_complete_servers}**\n"
                      f"Connected: **{len(self.bot.guilds)}**",
                inline=True
            )
            
            # Bot Performance
            embed.add_field(
                name="⚡ Performance",
                value=f"Latency: **{round(self.bot.latency * 1000)}ms**\n"
                      f"Uptime: **{self.get_uptime()}**\n"
                      f"Commands: **{len(self.bot.commands)}**",
                inline=True
            )
            
            # Economy Statistics
            if points_data:
                embed.add_field(
                    name="💰 Economy Statistics",
                    value=f"Total Points: **{int(points_data.get('total_points', 0)):,}**\n"
                          f"Total Earned: **{int(points_data.get('total_earned', 0)):,}**\n"
                          f"Total Spent: **{int(points_data.get('total_spent', 0)):,}**\n"
                          f"Avg Balance: **{int(points_data.get('avg_points', 0)):,}**\n"
                          f"Avg Trust: **{points_data.get('avg_trust', 50):.1f}/100**",
                    inline=False
                )
            
            # Cookie Statistics
            embed.add_field(
                name="🍪 Cookie Statistics",
                value=f"All-Time Claims: **{stats.get('all_time_claims', 0):,}**\n"
                      f"Cookie Types: **{len(stats.get('total_claims', {}))}**",
                inline=False
            )
            
            # Game Statistics
            if game_stats:
                game_text = []
                if game_stats.get("slots_played", 0) > 0:
                    game_text.append(f"Slots: **{game_stats.get('slots_played', 0):,}** played")
                if game_stats.get("bets_created", 0) > 0:
                    game_text.append(f"Bets: **{game_stats.get('bets_created', 0):,}** created")
                if game_stats.get("rob_attempts", 0) > 0:
                    game_text.append(f"Robs: **{game_stats.get('rob_attempts', 0):,}** attempts")
                if game_stats.get("divine_gambles", 0) > 0:
                    game_text.append(f"Divine: **{game_stats.get('divine_gambles', 0):,}** gambles")
                
                if game_text:
                    embed.add_field(
                        name="🎮 Game Statistics",
                        value="\n".join(game_text),
                        inline=False
                    )
            
            # Top cookies
            if stats.get("total_claims"):
                top_cookies = sorted(stats["total_claims"].items(), key=lambda x: x[1], reverse=True)[:5]
                if top_cookies:
                    cookie_text = "\n".join([f"{idx+1}. **{cookie}**: {count:,} claims" 
                                           for idx, (cookie, count) in enumerate(top_cookies)])
                    embed.add_field(name="🏆 Top Cookies", value=cookie_text, inline=False)
            
            # Memory usage
            embed.set_footer(text=f"Bot Version: 2.1 | Python {discord.__version__}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error in stats: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred while fetching statistics!", ephemeral=True)

    @commands.hybrid_command(name="broadcast", description="Send an announcement to all servers")
    @app_commands.describe(message="The message to broadcast")
    async def broadcast(self, ctx, *, message: str):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            # Confirmation embed
            confirm_embed = discord.Embed(
                title="📢 Broadcast Confirmation",
                description=f"Are you sure you want to send this message to **{len(self.bot.guilds)}** servers?",
                color=discord.Color.orange()
            )
            confirm_embed.add_field(name="Message Preview", value=message[:1024], inline=False)
            
            # Create confirmation view
            class ConfirmView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.confirmed = False
                
                @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
                async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("This isn't for you!", ephemeral=True)
                        return
                    self.confirmed = True
                    self.stop()
                
                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
                async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("This isn't for you!", ephemeral=True)
                        return
                    self.stop()
            
            view = ConfirmView()
            confirm_msg = await ctx.send(embed=confirm_embed, view=view)
            
            await view.wait()
            
            if not view.confirmed:
                cancel_embed = discord.Embed(
                    title="❌ Broadcast Cancelled",
                    description="The broadcast has been cancelled.",
                    color=discord.Color.red()
                )
                await confirm_msg.edit(embed=cancel_embed, view=None)
                return
            
            # Start broadcast
            await confirm_msg.edit(content="📡 Broadcasting...", embed=None, view=None)
            
            success = 0
            failed = 0
            
            broadcast_embed = discord.Embed(
                title="📢 Announcement from Cookie Bot",
                description=message,
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            broadcast_embed.set_footer(text="Cookie Bot Official Announcement", icon_url=self.bot.user.avatar.url)
            broadcast_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
            
            for guild in self.bot.guilds:
                try:
                    server = await self.db.servers.find_one({"server_id": guild.id})
                    sent = False
                    
                    # Try announcement channel first
                    if server and server.get("channels", {}).get("announcement"):
                        channel = self.bot.get_channel(server["channels"]["announcement"])
                        if channel and channel.permissions_for(guild.me).send_messages:
                            await channel.send(embed=broadcast_embed)
                            success += 1
                            sent = True
                            continue
                    
                    # Try other channels
                    if not sent:
                        for channel in guild.text_channels:
                            if channel.permissions_for(guild.me).send_messages:
                                await channel.send(embed=broadcast_embed)
                                success += 1
                                break
                        else:
                            failed += 1
                except Exception as e:
                    print(f"Failed to send to {guild.name}: {e}")
                    failed += 1
            
            # Final report
            result_embed = discord.Embed(
                title="📊 Broadcast Complete!",
                color=discord.Color.green() if failed == 0 else discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            result_embed.add_field(name="✅ Success", value=f"**{success}** servers", inline=True)
            result_embed.add_field(name="❌ Failed", value=f"**{failed}** servers", inline=True)
            result_embed.add_field(name="📊 Success Rate", value=f"**{success/(success+failed)*100:.1f}%**", inline=True)
            
            await confirm_msg.edit(content=None, embed=result_embed)
            
        except Exception as e:
            print(f"Error in broadcast: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred during broadcast!", ephemeral=True)
    
    @commands.hybrid_command(name="setrole", description="Configure role benefits")
    @app_commands.describe(
        role="The role to configure",
        daily_bonus="Daily bonus points",
        trust_multiplier="Trust score multiplier"
    )
    async def setrole(self, ctx, role: discord.Role, daily_bonus: int = 0, trust_multiplier: float = 1.0):
        try:
            if not await self.is_owner(ctx.author.id):
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured! Run /setup first.", ephemeral=True)
                return
            
            # Get default role template
            config = await self.db.config.find_one({"_id": "bot_config"})
            default_roles = config.get("default_roles", {})
            
            # Try to match with a default role type
            role_type = None
            for default_type, default_config in default_roles.items():
                if default_type.lower() in role.name.lower():
                    role_type = default_type
                    break
            
            if role_type:
                # Use template with custom overrides
                role_config = default_roles[role_type].copy()
                role_config["daily_bonus"] = daily_bonus
                role_config["trust_multiplier"] = trust_multiplier
            else:
                # Create custom configuration
                role_config = {
                    "name": role.name,
                    "description": f"Custom role configuration",
                    "emoji": "🎭",
                    "daily_bonus": daily_bonus,
                    "trust_multiplier": trust_multiplier,
                    "game_benefits": {
                        "slots_max_bet_bonus": 0,
                        "rob_success_bonus": 0,
                        "bet_profit_multiplier": 1.0
                    },
                    "cookie_access": {}
                }
            
            await self.db.servers.update_one(
                {"server_id": ctx.guild.id},
                {
                    "$set": {
                        f"roles.{role.id}": role_config,
                        "role_based": True
                    }
                }
            )
            
            embed = discord.Embed(
                title="🎭 Role Configured",
                description=f"Successfully configured {role.mention}",
                color=role.color
            )
            embed.add_field(name="Daily Bonus", value=f"{daily_bonus} points", inline=True)
            embed.add_field(name="Trust Multiplier", value=f"{trust_multiplier}x", inline=True)
            
            if role_type:
                embed.add_field(
                    name="Template Applied",
                    value=f"Using **{role_type}** template with cookie access",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"🎭 {ctx.author.mention} configured role {role.mention} with {daily_bonus} daily bonus and {trust_multiplier}x trust",
                discord.Color.blue()
            )
            
        except Exception as e:
            print(f"Error in setrole: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    def get_uptime(self):
        delta = datetime.now(timezone.utc) - self.bot.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
            
        return " ".join(parts)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))