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
                "blacklist_expires": None
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
                }
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
                    "blacklist_expires": None
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

async def setup(bot):
    await bot.add_cog(AdminCog(bot))