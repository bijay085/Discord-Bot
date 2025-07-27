# cogs/admin.py

import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone

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

    @commands.hybrid_command(name="givepoints", description="Give points to a user (Owner only)")
    async def givepoints(self, ctx, user: discord.Member, points: int):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        user_data = await self.db.users.find_one({"user_id": user.id})
        if not user_data:
            user_data = {
                "user_id": user.id,
                "username": str(user),
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
            await self.db.users.insert_one(user_data)
        
        if points > 0:
            await self.db.users.update_one(
                {"user_id": user.id},
                {
                    "$inc": {
                        "points": points,
                        "total_earned": points
                    }
                }
            )
            action = "gave"
            color = discord.Color.green()
        else:
            await self.db.users.update_one(
                {"user_id": user.id},
                {
                    "$inc": {"points": points}
                }
            )
            action = "removed"
            color = discord.Color.red()
        
        new_balance = user_data.get("points", 0) + points
        
        embed = discord.Embed(
            title=f"✅ Points {action.title()}!",
            description=f"{action.title()} **{abs(points)}** points {action == 'gave' and 'to' or 'from'} {user.mention}",
            color=color
        )
        embed.add_field(name="New Balance", value=f"**{new_balance}** points", inline=True)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"💰 {ctx.author.mention} {action} **{abs(points)}** points {action == 'gave' and 'to' or 'from'} {user.mention}",
            color
        )

    @commands.hybrid_command(name="checkpoints", description="Check user's points (Owner only)")
    async def checkpoints(self, ctx, user: discord.Member):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        user_data = await self.db.users.find_one({"user_id": user.id})
        if not user_data:
            await ctx.send(f"❌ {user.mention} not found in database!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"💰 Points Check: {user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Points", value=f"**{user_data.get('points', 0)}**", inline=True)
        embed.add_field(name="Total Earned", value=f"**{user_data.get('total_earned', 0)}**", inline=True)
        embed.add_field(name="Total Spent", value=f"**{user_data.get('total_spent', 0)}**", inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="maintenance", description="Toggle maintenance mode (Owner only)")
    async def maintenance(self, ctx, mode: bool):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await self.db.config.update_one(
            {"_id": "bot_config"},
            {"$set": {"maintenance_mode": mode}}
        )
        
        status = "enabled" if mode else "disabled"
        embed = discord.Embed(
            title=f"🔧 Maintenance Mode {status.title()}",
            description=f"Bot is now {'in maintenance mode' if mode else 'operational'}",
            color=discord.Color.orange() if mode else discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🔧 {ctx.author.mention} {status} maintenance mode",
            discord.Color.orange() if mode else discord.Color.green()
        )

    @commands.hybrid_command(name="blacklist", description="Blacklist a user (Owner only)")
    async def blacklist(self, ctx, user: discord.Member, days: int = 30):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        expire_date = datetime.now(timezone.utc) + timedelta(days=days)
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "blacklisted": True,
                    "blacklist_expires": expire_date
                },
                "$inc": {"trust_score": -20}
            },
            upsert=True
        )
        
        embed = discord.Embed(
            title="🚫 User Blacklisted",
            description=f"{user.mention} has been blacklisted for **{days}** days",
            color=discord.Color.red()
        )
        embed.add_field(name="Expires", value=f"<t:{int(expire_date.timestamp())}:R>", inline=True)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🚫 {ctx.author.mention} blacklisted {user.mention} for {days} days",
            discord.Color.red()
        )

    @commands.hybrid_command(name="unblacklist", description="Remove user from blacklist (Owner only)")
    async def unblacklist(self, ctx, user: discord.Member):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "blacklisted": False,
                    "blacklist_expires": None,
                    "failed_attempts": 0,
                    "last_failed_attempt": None
                }
            }
        )
        
        embed = discord.Embed(
            title="✅ User Unblacklisted",
            description=f"{user.mention} has been removed from blacklist",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"✅ {ctx.author.mention} unblacklisted {user.mention}",
            discord.Color.green()
        )

    @commands.hybrid_command(name="stats", description="View bot statistics (Owner only)")
    async def stats(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        total_users = await self.db.users.count_documents({})
        blacklisted_users = await self.db.users.count_documents({"blacklisted": True})
        total_servers = await self.db.servers.count_documents({})
        
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        if not stats:
            stats = {"all_time_claims": 0, "total_claims": {}}
        
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="Total Users", value=f"**{total_users}**", inline=True)
        embed.add_field(name="Blacklisted", value=f"**{blacklisted_users}**", inline=True)
        embed.add_field(name="Total Servers", value=f"**{total_servers}**", inline=True)
        
        embed.add_field(name="All Time Claims", value=f"**{stats.get('all_time_claims', 0)}**", inline=True)
        embed.add_field(name="Active Servers", value=f"**{len(self.bot.guilds)}**", inline=True)
        embed.add_field(name="Bot Latency", value=f"**{round(self.bot.latency * 1000)}ms**", inline=True)
        
        if stats.get("total_claims"):
            top_cookies = sorted(stats["total_claims"].items(), key=lambda x: x[1], reverse=True)[:5]
            if top_cookies:
                cookie_text = "\n".join([f"• {cookie}: **{count}**" for cookie, count in top_cookies])
                embed.add_field(name="Top Cookies", value=cookie_text, inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="broadcast", description="Send message to all servers (Owner only)")
    async def broadcast(self, ctx, *, message: str):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        success = 0
        failed = 0
        
        embed = discord.Embed(
            title="📢 Announcement from Bot Owner",
            description=message,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Cookie Bot Announcement")
        
        for guild in self.bot.guilds:
            try:
                server = await self.db.servers.find_one({"server_id": guild.id})
                if server and server.get("channels", {}).get("announcement"):
                    channel = self.bot.get_channel(server["channels"]["announcement"])
                    if channel:
                        await channel.send(embed=embed)
                        success += 1
                        continue
                
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        await channel.send(embed=embed)
                        success += 1
                        break
                else:
                    failed += 1
            except:
                failed += 1
        
        await ctx.send(f"✅ Broadcast complete!\nSuccess: **{success}**\nFailed: **{failed}**")

    @commands.hybrid_command(name="setfilter", description="Configure bot filters (Owner only)")
    async def setfilter(self, ctx, filter_type: str, value: str):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        valid_filters = {
            "min_account_age": "Minimum account age in days",
            "min_server_days": "Minimum days in server",
            "min_trust_score": "Minimum trust score required",
            "rate_limit_claims": "Max claims per window",
            "rate_limit_window": "Rate limit window in minutes",
            "max_failed_attempts": "Max failed attempts before timeout",
            "require_avatar": "Require profile avatar (true/false)",
            "feedback_minutes": "Minutes to submit feedback"
        }
        
        if filter_type not in valid_filters:
            embed = discord.Embed(
                title="❌ Invalid Filter Type",
                description="Valid filters:\n" + "\n".join([f"`{k}` - {v}" for k, v in valid_filters.items()]),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        try:
            if filter_type == "require_avatar":
                value = value.lower() == "true"
            else:
                value = int(value)
            
            await self.db.config.update_one(
                {"_id": "bot_config"},
                {"$set": {filter_type: value}}
            )
            
            embed = discord.Embed(
                title="✅ Filter Updated",
                description=f"**{filter_type}** set to **{value}**",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"🔧 {ctx.author.mention} updated filter: **{filter_type}** = **{value}**",
                discord.Color.blue()
            )
            
        except ValueError:
            await ctx.send("❌ Invalid value! Use a number for this filter.", ephemeral=True)

    @commands.hybrid_command(name="viewfilters", description="View current filter settings (Owner only)")
    async def viewfilters(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        
        embed = discord.Embed(
            title="🛡️ Current Filter Settings",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Account Requirements",
            value=(
                f"Min Account Age: **{config.get('min_account_age_days', 7)}** days\n"
                f"Min Server Days: **{config.get('min_server_days', 1)}** days\n"
                f"Min Trust Score: **{config.get('min_trust_score', 20)}**/100\n"
                f"Require Avatar: **{config.get('require_avatar', True)}**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Rate Limits",
            value=(
                f"Max Claims: **{config.get('rate_limit_claims', 3)}** per window\n"
                f"Window Size: **{config.get('rate_limit_window', 60)}** minutes\n"
                f"Max Failed Attempts: **{config.get('max_failed_attempts', 5)}**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Other Settings",
            value=(
                f"Feedback Deadline: **{config.get('feedback_minutes', 15)}** minutes\n"
                f"Blacklist Duration: **{config.get('blacklist_days', 30)}** days"
            ),
            inline=False
        )
        
        suspicious_patterns = config.get('suspicious_username_patterns', [])
        if suspicious_patterns:
            embed.add_field(
                name="Suspicious Username Patterns",
                value=", ".join([f"`{p}`" for p in suspicious_patterns[:10]]),
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="addsuspicious", description="Add suspicious username pattern (Owner only)")
    async def addsuspicious(self, ctx, pattern: str):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await self.db.config.update_one(
            {"_id": "bot_config"},
            {"$addToSet": {"suspicious_username_patterns": pattern.lower()}}
        )
        
        embed = discord.Embed(
            title="✅ Pattern Added",
            description=f"Added `{pattern}` to suspicious username patterns",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🛡️ {ctx.author.mention} added suspicious pattern: `{pattern}`",
            discord.Color.blue()
        )

    @commands.hybrid_command(name="removesuspicious", description="Remove suspicious username pattern (Owner only)")
    async def removesuspicious(self, ctx, pattern: str):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await self.db.config.update_one(
            {"_id": "bot_config"},
            {"$pull": {"suspicious_username_patterns": pattern.lower()}}
        )
        
        embed = discord.Embed(
            title="✅ Pattern Removed",
            description=f"Removed `{pattern}` from suspicious username patterns",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="checkuser", description="Check if a user passes filters (Owner only)")
    async def checkuser(self, ctx, user: discord.Member):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        cookie_cog = self.bot.get_cog("CookieCog")
        if not cookie_cog:
            await ctx.send("❌ Cookie cog not loaded!", ephemeral=True)
            return
        
        passed, reason = await cookie_cog.check_user_filters(ctx, user)
        
        user_data = await self.db.users.find_one({"user_id": user.id})
        
        embed = discord.Embed(
            title=f"🔍 Filter Check: {user.display_name}",
            color=discord.Color.green() if passed else discord.Color.red()
        )
        
        embed.add_field(name="Result", value="✅ PASSED" if passed else "❌ FAILED", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        account_age = datetime.now(timezone.utc) - user.created_at.replace(tzinfo=timezone.utc)
        server_age = datetime.now(timezone.utc) - user.joined_at.replace(tzinfo=timezone.utc) if user.joined_at else "Unknown"
        
        embed.add_field(name="Account Age", value=f"{account_age.days} days", inline=True)
        embed.add_field(name="Server Age", value=f"{server_age.days if server_age != 'Unknown' else 'Unknown'} days", inline=True)
        embed.add_field(name="Has Avatar", value="✅" if user.avatar else "❌", inline=True)
        
        if user_data:
            embed.add_field(name="Trust Score", value=f"{user_data.get('trust_score', 50)}/100", inline=True)
            embed.add_field(name="Failed Attempts", value=user_data.get('failed_attempts', 0), inline=True)
            embed.add_field(name="Total Claims", value=user_data.get('total_claims', 0), inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="resetfailed", description="Reset failed attempts for a user (Owner only)")
    async def resetfailed(self, ctx, user: discord.Member):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "failed_attempts": 0,
                    "last_failed_attempt": None
                },
                "$unset": {"failed_attempt_log": ""}
            }
        )
        
        embed = discord.Embed(
            title="✅ Failed Attempts Reset",
            description=f"Reset failed attempts for {user.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🔧 {ctx.author.mention} reset failed attempts for {user.mention}",
            discord.Color.green()
        )

    @commands.hybrid_command(name="settrust", description="Set user's trust score (Owner only)")
    async def settrust(self, ctx, user: discord.Member, score: int):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        if score < 0 or score > 100:
            await ctx.send("❌ Trust score must be between 0 and 100!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {"$set": {"trust_score": score}},
            upsert=True
        )
        
        embed = discord.Embed(
            title="✅ Trust Score Updated",
            description=f"Set {user.mention}'s trust score to **{score}/100**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🔧 {ctx.author.mention} set {user.mention}'s trust score to **{score}/100**",
            discord.Color.blue()
        )

async def setup(bot):
    await bot.add_cog(AdminCog(bot))