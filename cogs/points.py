# cogs/points.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
import traceback
from typing import Optional

class PointsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        
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
                "daily_claims": {},  # For cookie daily limits
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
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def get_user_role_config(self, member: discord.Member, server: dict) -> dict:
        """Get the best role configuration for a user based on role hierarchy"""
        if not server.get("role_based"):
            return {}
            
        best_config = {}
        highest_priority = -1
        
        # Get fresh server data to ensure we have latest role configs
        server = await self.db.servers.find_one({"server_id": member.guild.id})
        if not server or not server.get("roles"):
            return {}
        
        for role in member.roles:
            role_config = server["roles"].get(str(role.id))
            if role_config and isinstance(role_config, dict):
                # Check if this role has better priority (position in hierarchy)
                if role.position > highest_priority:
                    highest_priority = role.position
                    best_config = role_config
        
        return best_config
    
    @commands.hybrid_command(name="daily", description="Claim your daily points with role bonuses")
    async def daily(self, ctx):
        try:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server or not server.get("enabled"):
                embed = discord.Embed(
                    title="❌ Bot Disabled",
                    description="The bot is not enabled in this server!",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Contact an admin to enable the bot")
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.get_or_create_user(ctx.author.id, str(ctx.author))
            
            if user_data.get("daily_claimed"):
                daily_claimed = user_data["daily_claimed"]
                # Ensure daily_claimed is timezone-aware
                if daily_claimed.tzinfo is None:
                    daily_claimed = daily_claimed.replace(tzinfo=timezone.utc)
                
                # Fixed daily reset logic - check if it's a new day
                now = datetime.now(timezone.utc)
                last_claim_day = daily_claimed.replace(hour=0, minute=0, second=0, microsecond=0)
                current_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if current_day <= last_claim_day:
                    # Calculate time until next daily (midnight UTC)
                    tomorrow = current_day + timedelta(days=1)
                    remaining = tomorrow - now
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int((remaining.total_seconds() % 3600) // 60)
                    
                    embed = discord.Embed(
                        title="⏰ Daily Already Claimed!",
                        description=f"You need to wait until the next day to claim again.",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="Time Remaining", value=f"**{hours}h {minutes}m**", inline=True)
                    embed.add_field(name="Next Claim", value=f"<t:{int(tomorrow.timestamp())}:R>", inline=True)
                    embed.add_field(name="Last Claimed", value=f"<t:{int(daily_claimed.timestamp())}:R>", inline=True)
                    embed.set_footer(text="Daily resets at midnight UTC!")
                    
                    await ctx.send(embed=embed, ephemeral=True)
                    return
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            base_daily_points = config["point_rates"]["daily"]
            
            # Get role bonus
            role_config = await self.get_user_role_config(ctx.author, server)
            role_bonus = 0
            role_name = None
            trust_multiplier = 1.0
            
            if role_config:
                role_bonus = role_config.get("daily_bonus", 0)
                role_name = role_config.get("name", "Unknown")
                trust_multiplier = role_config.get("trust_multiplier", 1.0)
            
            total_daily_points = base_daily_points + role_bonus
            
            # Apply trust multiplier if enabled
            if server.get("settings", {}).get("trust_affects_daily", False) and trust_multiplier > 1.0:
                bonus_from_trust = int((total_daily_points * trust_multiplier) - total_daily_points)
                total_daily_points = int(total_daily_points * trust_multiplier)
            else:
                bonus_from_trust = 0
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$set": {"daily_claimed": datetime.now(timezone.utc)},
                    "$inc": {
                        "points": total_daily_points,
                        "total_earned": total_daily_points
                    }
                }
            )
            
            new_points = user_data["points"] + total_daily_points
            
            embed = discord.Embed(
                title="✅ Daily Points Claimed!",
                description=f"You received your daily reward!",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Show breakdown
            embed.add_field(name="🎁 Base Daily", value=f"{base_daily_points} points", inline=True)
            
            if role_bonus > 0:
                embed.add_field(name="🎭 Role Bonus", value=f"+{role_bonus} points", inline=True)
            
            if bonus_from_trust > 0:
                embed.add_field(name="✨ Trust Bonus", value=f"+{bonus_from_trust} points", inline=True)
            
            embed.add_field(name="💰 Total Reward", value=f"**{total_daily_points}** points", inline=False)
            embed.add_field(name="💳 New Balance", value=f"**{new_points}** points", inline=True)
            embed.add_field(name="⏰ Next Daily", value="Available tomorrow at midnight UTC", inline=True)
            
            if role_name:
                embed.set_footer(text=f"Claimed with {role_name} benefits • Total earned: {user_data['total_earned'] + total_daily_points} points")
            else:
                embed.set_footer(text=f"Total earned: {user_data['total_earned'] + total_daily_points} points")
            
            await ctx.send(embed=embed, ephemeral=True)
            
            await self.log_action(
                ctx.guild.id,
                f"💰 {ctx.author.mention} claimed daily points [+{total_daily_points}] [Role: {role_name or 'None'}]",
                discord.Color.green()
            )
        except Exception as e:
            print(f"Error in daily command: {traceback.format_exc()}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while claiming your daily points!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
    
    @commands.hybrid_command(name="points", description="Check your points and stats")
    async def points(self, ctx, user: discord.Member = None):
        try:
            target = user or ctx.author
            user_data = await self.get_or_create_user(target.id, str(target))
            
            # Get server and role information
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            role_config = None
            if server and server.get("role_based"):
                role_config = await self.get_user_role_config(target, server)
            
            embed = discord.Embed(
                title=f"💰 {target.display_name}'s Account",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            
            embed.add_field(name="Current Points", value=f"**{user_data.get('points', 0):,}**", inline=True)
            embed.add_field(name="Total Earned", value=f"**{user_data.get('total_earned', 0):,}**", inline=True)
            embed.add_field(name="Total Spent", value=f"**{user_data.get('total_spent', 0):,}**", inline=True)
            
            # Apply trust multiplier for display
            trust_score = user_data.get('trust_score', 50)
            if role_config and role_config.get('trust_multiplier', 1.0) > 1.0:
                effective_trust = min(100, trust_score * role_config['trust_multiplier'])
                trust_display = f"**{trust_score}** (×{role_config['trust_multiplier']} = {effective_trust:.1f})"
            else:
                trust_display = f"**{trust_score}/100**"
                
            trust_emoji = "🟢" if trust_score >= 80 else "🟡" if trust_score >= 50 else "🔴"
            embed.add_field(name="Trust Score", value=f"{trust_emoji} {trust_display}", inline=True)
            embed.add_field(name="Total Claims", value=f"**{user_data.get('total_claims', 0):,}**", inline=True)
            embed.add_field(name="This Week", value=f"**{user_data.get('weekly_claims', 0):,}**", inline=True)
            
            # Show role benefits
            if role_config:
                embed.add_field(
                    name="🎭 Active Role",
                    value=f"**{role_config.get('name', 'Unknown')}**",
                    inline=True
                )
                
                if role_config.get('daily_bonus', 0) > 0:
                    embed.add_field(
                        name="🎁 Daily Bonus",
                        value=f"+{role_config['daily_bonus']} points",
                        inline=True
                    )
                
                # Count accessible cookies
                accessible = 0
                if "cookie_access" in role_config:
                    for cookie, access in role_config["cookie_access"].items():
                        if access.get("enabled", False):
                            accessible += 1
                    embed.add_field(
                        name="🍪 Cookie Access",
                        value=f"{accessible} types",
                        inline=True
                    )
            
            if user_data.get("cookie_claims"):
                top_cookies = sorted(user_data["cookie_claims"].items(), key=lambda x: x[1], reverse=True)[:3]
                if top_cookies:
                    fav_text = "\n".join([f"{idx+1}. **{cookie}**: {count}" for idx, (cookie, count) in enumerate(top_cookies)])
                    embed.add_field(name="🍪 Favorite Cookies", value=fav_text, inline=False)
            
            # Show daily claim status
            if user_data.get("daily_claimed"):
                daily_claimed = user_data["daily_claimed"]
                if daily_claimed.tzinfo is None:
                    daily_claimed = daily_claimed.replace(tzinfo=timezone.utc)
                    
                now = datetime.now(timezone.utc)
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                
                if daily_claimed.date() == now.date():
                    embed.add_field(
                        name="📅 Daily Status",
                        value=f"✅ Claimed today\nNext: <t:{int(tomorrow.timestamp())}:R>",
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="📅 Daily Status",
                        value="❌ Not claimed today\nUse `/daily` now!",
                        inline=True
                    )
            
            account_created = user_data.get('account_created', user_data.get('first_seen', datetime.now(timezone.utc)))
            if isinstance(account_created, datetime):
                embed.set_footer(text=f"Account created: {account_created.strftime('%B %d, %Y')}")
            else:
                embed.set_footer(text="Account created: Unknown")
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in points command: {e}")
            import traceback
            print(traceback.format_exc())
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="getpoints", description="Ways to earn points")
    async def getpoints(self, ctx):
        try:
            config = await self.db.config.find_one({"_id": "bot_config"})
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            
            embed = discord.Embed(
                title="💰 How to Earn Points",
                description="Here are all the ways to get points:",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            # Base methods
            embed.add_field(
                name="🎁 Daily Rewards",
                value=f"`/daily` - Get **{config['point_rates']['daily']}** base points every 24 hours",
                inline=False
            )
            
            embed.add_field(
                name="👥 Invite Friends",
                value=f"Invite new members - Get **{config['point_rates']['invite']}** points per invite\n"
                      f"They must get <@&1349289354329198623> role",
                inline=False
            )
            
            # Role bonuses
            if server and server.get("role_based") and server.get("roles"):
                role_bonuses = []
                for role_id, role_config in server["roles"].items():
                    if isinstance(role_config, dict) and role_config.get("daily_bonus", 0) > 0:
                        role_name = role_config.get("name", "Unknown")
                        daily_bonus = role_config["daily_bonus"]
                        role_bonuses.append(f"• **{role_name}**: +{daily_bonus} daily bonus")
                
                if role_bonuses:
                    embed.add_field(
                        name="🎭 Role Daily Bonuses",
                        value="\n".join(role_bonuses[:5]),
                        inline=False
                    )
            
            embed.add_field(
                name="🚀 Server Boost",
                value="Boost the server - Get special role with amazing benefits!",
                inline=False
            )
            
            embed.add_field(
                name="🎮 Play Games",
                value=(
                    "• **Slots**: Win up to 50x your bet\n"
                    "• **Betting**: Win number guessing games\n"
                    "• **Robbing**: Steal from others (risky!)\n"
                    "• **Giveaways**: Join point giveaways"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💎 Special Roles Benefits",
                value=(
                    "Higher roles get:\n"
                    "• Daily bonus points\n"
                    "• Lower cookie costs\n"
                    "• Reduced cooldowns\n"
                    "• Higher daily limits\n"
                    "• Trust multipliers\n"
                    "• Game bonuses"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📢 Events",
                value="Participate in special events and giveaways!",
                inline=False
            )
            
            main_invite = config.get("main_server_invite", "")
            embed.set_footer(text=f"Need help? Join: {main_invite}")
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in getpoints command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="status", description="Check detailed user status")
    @app_commands.describe(user="The user to check status for (leave empty for yourself)")
    async def status(self, ctx, user: discord.Member = None):
        try:
            if user is None:
                user = ctx.author
            
            user_data = await self.db.users.find_one({"user_id": user.id})
            if not user_data:
                embed = discord.Embed(
                    title="❌ User Not Found",
                    description="This user hasn't used the bot yet!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            role_config = None
            if server and server.get("role_based"):
                role_config = await self.get_user_role_config(user, server)
            
            status_color = discord.Color.red() if user_data.get("blacklisted") else discord.Color.green()
            status_emoji = "🚫" if user_data.get("blacklisted") else "✅"
            
            embed = discord.Embed(
                title=f"📊 Status: {user.display_name}",
                color=status_color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            if user_data.get("blacklisted"):
                expires = user_data.get("blacklist_expires")
                if expires:
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    remaining = expires - datetime.now(timezone.utc)
                    days = remaining.days
                    hours = remaining.seconds // 3600
                    embed.add_field(
                        name="⛔ Blacklist Status",
                        value=f"**BLACKLISTED**\nExpires: <t:{int(expires.timestamp())}:R>\nTime left: {days}d {hours}h",
                        inline=False
                    )
                else:
                    embed.add_field(name="⛔ Blacklist Status", value="**PERMANENTLY BLACKLISTED**", inline=False)
            else:
                embed.add_field(name="Status", value=f"{status_emoji} **Active**", inline=False)
            
            # Role information
            if role_config:
                embed.add_field(
                    name="🎭 Active Role",
                    value=f"**{role_config.get('name', 'Unknown')}**",
                    inline=True
                )
                
                # Show role perks
                perks = []
                if role_config.get("daily_bonus", 0) > 0:
                    perks.append(f"Daily: +{role_config['daily_bonus']}")
                if role_config.get("trust_multiplier", 1.0) > 1.0:
                    perks.append(f"Trust: ×{role_config['trust_multiplier']}")
                
                if perks:
                    embed.add_field(
                        name="✨ Role Perks",
                        value=" | ".join(perks),
                        inline=True
                    )
            
            embed.add_field(name="💰 Points", value=f"**{user_data.get('points', 0):,}**", inline=True)
            embed.add_field(name="🍪 Total Claims", value=f"**{user_data.get('total_claims', 0):,}**", inline=True)
            embed.add_field(name="👥 Invites", value=f"**{user_data.get('invite_count', 0):,}**", inline=True)
            
            trust_emoji = "🟢" if user_data.get('trust_score', 50) >= 80 else "🟡" if user_data.get('trust_score', 50) >= 50 else "🔴"
            embed.add_field(name="🏆 Trust Score", value=f"{trust_emoji} **{user_data.get('trust_score', 50)}/100**", inline=True)
            embed.add_field(name="📈 Total Earned", value=f"**{user_data.get('total_earned', 0):,}**", inline=True)
            embed.add_field(name="📉 Total Spent", value=f"**{user_data.get('total_spent', 0):,}**", inline=True)
            
            # Daily claims breakdown
            if user_data.get("daily_claims"):
                daily_text = []
                for cookie_type, claim_data in list(user_data["daily_claims"].items())[:3]:
                    count = claim_data.get("count", 0)
                    daily_text.append(f"**{cookie_type}**: {count} today")
                
                if daily_text:
                    embed.add_field(
                        name="📅 Today's Claims",
                        value="\n".join(daily_text),
                        inline=False
                    )
            
            if user_data.get("last_claim"):
                last_claim = user_data["last_claim"]
                claim_date = last_claim.get('date', datetime.now(timezone.utc))
                feedback_emoji = "✅" if last_claim.get("feedback_given") else "❌"
                
                embed.add_field(
                    name="🍪 Last Cookie",
                    value=f"Type: **{last_claim.get('type', 'Unknown')}**\n"
                          f"Date: <t:{int(claim_date.timestamp())}:R>\n"
                          f"Feedback: {feedback_emoji} {'Given' if last_claim.get('feedback_given') else 'Pending'}",
                    inline=False
                )
            
            embed.set_footer(text=f"User ID: {user.id} • Joined: {user_data.get('first_seen', datetime.now(timezone.utc)).strftime('%Y-%m-%d')}")
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in status command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="help", description="Show all available commands")
    async def help_command(self, ctx):
        try:
            config = await self.db.config.find_one({"_id": "bot_config"})
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            
            embed = discord.Embed(
                title="🍪 Cookie Bot Help",
                description="Complete command list and guide",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            embed.add_field(
                name="📍 Basic Commands",
                value=(
                    "`/cookie <type>` - Claim a cookie (role-based access)\n"
                    "`/daily` - Get daily points + role bonus\n"
                    "`/points` - Check your balance\n"
                    "`/status [@user]` - Check detailed status\n"
                    "`/stock [type]` - Check cookie stock\n"
                    "`/getpoints` - How to earn points\n"
                    "`/feedback` - Submit feedback\n"
                    "`/refresh` - Refresh role benefits\n"
                    "`/help` - Show this message"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🍪 Cookie Types",
                value=(
                    "Access depends on your role:\n"
                    "• **Streaming**: netflix, prime, jiohotstar, peacock, canalplus\n"
                    "• **Music**: spotify, crunchyroll\n"
                    "• **Premium**: tradingview, chatgpt, claude"
                ),
                inline=False
            )
            
            embed.add_field(
                name="⚠️ Important Rules",
                value=(
                    "• Submit feedback within **15 minutes**\n"
                    "• Post screenshot in feedback channel\n"
                    "• No feedback = **30 day blacklist**\n"
                    "• Enable DMs to receive cookies\n"
                    "• Daily limits apply per cookie type"
                ),
                inline=False
            )
            
            # Show role hierarchy if enabled
            if server and server.get("role_based") and server.get("roles"):
                role_list = []
                for role_id, role_config in server["roles"].items():
                    if isinstance(role_config, dict):
                        role_name = role_config.get("name", "Unknown")
                        daily_bonus = role_config.get("daily_bonus", 0)
                        role_list.append(f"• **{role_name}**: +{daily_bonus} daily")
                
                if role_list:
                    embed.add_field(
                        name="💎 Role Benefits",
                        value="\n".join(role_list[:5]) + ("\n*And more...*" if len(role_list) > 5 else ""),
                        inline=False
                    )
            
            embed.add_field(
                name="🎮 Game Commands",
                value=(
                    "`/games` - View all games guide\n"
                    "`/slots play` - Play slot machine\n"
                    "`/bet` - Start betting game\n"
                    "`/rob` - Rob another user\n"
                    "`/gamble divine` - Ultimate risk"
                ),
                inline=False
            )
            
            main_invite = config.get("main_server_invite", "")
            embed.set_footer(text=f"Support Server: {main_invite}")
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in help command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="fixusers", description="Fix missing user fields (Admin only)")
    @commands.has_permissions(administrator=True)
    async def fixusers(self, ctx):
        try:
            await ctx.defer()
            
            fixed_count = 0
            async for user in self.db.users.find():
                update_fields = {}
                
                # Check and add missing fields
                if 'points' not in user:
                    update_fields['points'] = 0
                if 'total_earned' not in user:
                    update_fields['total_earned'] = user.get('points', 0)
                if 'total_spent' not in user:
                    update_fields['total_spent'] = 0
                if 'trust_score' not in user:
                    update_fields['trust_score'] = 50
                if 'account_created' not in user:
                    update_fields['account_created'] = user.get('first_seen', datetime.now(timezone.utc))
                if 'total_claims' not in user:
                    update_fields['total_claims'] = 0
                if 'weekly_claims' not in user:
                    update_fields['weekly_claims'] = 0
                if 'cookie_claims' not in user:
                    update_fields['cookie_claims'] = {}
                if 'daily_claims' not in user:
                    update_fields['daily_claims'] = {}
                if 'preferences' not in user:
                    update_fields['preferences'] = {
                        "dm_notifications": True,
                        "claim_confirmations": True,
                        "feedback_reminders": True
                    }
                if 'statistics' not in user:
                    update_fields['statistics'] = {
                        "feedback_streak": 0,
                        "perfect_ratings": 0,
                        "favorite_cookie": None
                    }
                
                if update_fields:
                    await self.db.users.update_one(
                        {"user_id": user["user_id"]},
                        {"$set": update_fields}
                    )
                    fixed_count += 1
            
            embed = discord.Embed(
                title="✅ User Data Fixed",
                description=f"Updated **{fixed_count}** users with missing fields",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error in fixusers command: {e}")
            await ctx.send("❌ An error occurred while fixing user data!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PointsCog(bot))