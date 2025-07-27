import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
import traceback

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
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    @commands.hybrid_command(name="daily", description="Claim your daily points")
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
                time_passed = datetime.now(timezone.utc) - user_data["daily_claimed"]
                if time_passed < timedelta(hours=24):
                    remaining = timedelta(hours=24) - time_passed
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int((remaining.total_seconds() % 3600) // 60)
                    
                    embed = discord.Embed(
                        title="⏰ Daily Already Claimed!",
                        description=f"You need to wait before claiming again.",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="Time Remaining", value=f"**{hours}h {minutes}m**", inline=True)
                    embed.add_field(name="Next Claim", value=f"<t:{int((user_data['daily_claimed'] + timedelta(hours=24)).timestamp())}:R>", inline=True)
                    embed.set_footer(text="Come back tomorrow!")
                    
                    await ctx.send(embed=embed, ephemeral=True)
                    return
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            daily_points = config["point_rates"]["daily"]
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$set": {"daily_claimed": datetime.now(timezone.utc)},
                    "$inc": {
                        "points": daily_points,
                        "total_earned": daily_points
                    }
                }
            )
            
            new_points = user_data["points"] + daily_points
            
            embed = discord.Embed(
                title="✅ Daily Points Claimed!",
                description=f"You received your daily reward!",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Reward", value=f"**+{daily_points}** points", inline=True)
            embed.add_field(name="New Balance", value=f"**{new_points}** points", inline=True)
            embed.add_field(name="Next Daily", value="Available in 24 hours", inline=True)
            embed.set_footer(text=f"Total earned: {user_data['total_earned'] + daily_points} points")
            
            await ctx.send(embed=embed, ephemeral=True)
            
            await self.log_action(
                ctx.guild.id,
                f"💰 {ctx.author.mention} claimed daily points [+{daily_points}]",
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
            
            embed = discord.Embed(
                title=f"💰 {target.display_name}'s Account",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            
            embed.add_field(name="Current Points", value=f"**{user_data.get('points', 0):,}**", inline=True)
            embed.add_field(name="Total Earned", value=f"**{user_data.get('total_earned', 0):,}**", inline=True)
            embed.add_field(name="Total Spent", value=f"**{user_data.get('total_spent', 0):,}**", inline=True)
            
            trust_emoji = "🟢" if user_data.get('trust_score', 50) >= 80 else "🟡" if user_data.get('trust_score', 50) >= 50 else "🔴"
            embed.add_field(name="Trust Score", value=f"{trust_emoji} **{user_data.get('trust_score', 50)}/100**", inline=True)
            embed.add_field(name="Total Claims", value=f"**{user_data.get('total_claims', 0):,}**", inline=True)
            embed.add_field(name="This Week", value=f"**{user_data.get('weekly_claims', 0):,}**", inline=True)
            
            if user_data.get("cookie_claims"):
                top_cookies = sorted(user_data["cookie_claims"].items(), key=lambda x: x[1], reverse=True)[:3]
                if top_cookies:
                    fav_text = "\n".join([f"{idx+1}. **{cookie}**: {count}" for idx, (cookie, count) in enumerate(top_cookies)])
                    embed.add_field(name="🍪 Favorite Cookies", value=fav_text, inline=False)
            
            embed.set_footer(text=f"Account created: {user_data['account_created'].strftime('%B %d, %Y')}")
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in points command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="getpoints", description="Ways to earn points")
    async def getpoints(self, ctx):
        try:
            config = await self.db.config.find_one({"_id": "bot_config"})
            
            embed = discord.Embed(
                title="💰 How to Earn Points",
                description="Here are all the ways to get points:",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            embed.add_field(
                name="🎁 Daily Rewards",
                value=f"`/daily` - Get **{config['point_rates']['daily']}** points every 24 hours",
                inline=False
            )
            
            embed.add_field(
                name="👥 Invite Friends",
                value=f"Invite new members - Get **{config['point_rates']['invite']}** points per invite\n"
                      f"They must get <@&1349289354329198623> role",
                inline=False
            )
            
            embed.add_field(
                name="🚀 Server Boost",
                value="Boost the server - Get special role with **FREE** cookies!",
                inline=False
            )
            
            embed.add_field(
                name="💎 Special Roles",
                value=(
                    "• **Free Role**: Default costs\n"
                    "• **Premium Role**: Reduced costs\n"
                    "• **VIP Role**: Very low costs\n"
                    "• **Booster Role**: FREE cookies!"
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
            
            embed.add_field(name="💰 Points", value=f"**{user_data.get('points', 0):,}**", inline=True)
            embed.add_field(name="🍪 Total Claims", value=f"**{user_data.get('total_claims', 0):,}**", inline=True)
            embed.add_field(name="👥 Invites", value=f"**{user_data.get('invite_count', 0):,}**", inline=True)
            
            trust_emoji = "🟢" if user_data.get('trust_score', 50) >= 80 else "🟡" if user_data.get('trust_score', 50) >= 50 else "🔴"
            embed.add_field(name="🏆 Trust Score", value=f"{trust_emoji} **{user_data.get('trust_score', 50)}/100**", inline=True)
            embed.add_field(name="📈 Total Earned", value=f"**{user_data.get('total_earned', 0):,}**", inline=True)
            embed.add_field(name="📉 Total Spent", value=f"**{user_data.get('total_spent', 0):,}**", inline=True)
            
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
                    "`/cookie <type>` - Claim a cookie\n"
                    "`/daily` - Get daily points\n"
                    "`/points` - Check your balance\n"
                    "`/status [@user]` - Check detailed status\n"
                    "`/stock [type]` - Check cookie stock\n"
                    "`/getpoints` - How to earn points\n"
                    "`/feedback` - Submit feedback\n"
                    "`/help` - Show this message"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🍪 Cookie Types",
                value=(
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
                    "• Enable DMs to receive cookies"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💎 Role Benefits",
                value=(
                    "• **Free**: Default prices & cooldowns\n"
                    "• **Premium**: Lower costs & faster cooldowns\n"
                    "• **VIP**: Very low costs & minimal cooldowns\n"
                    "• **Booster**: FREE cookies & no cooldowns!"
                ),
                inline=False
            )
            
            main_invite = config.get("main_server_invite", "")
            embed.set_footer(text=f"Support Server: {main_invite}")
            
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in help command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PointsCog(bot))