import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import asyncio

class AdminModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.warnings = {}
        
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    async def is_admin(self, user: discord.Member) -> bool:
        if await self.is_owner(user.id):
            return True
        if user.guild_permissions.administrator:
            return True
        server = await self.db.servers.find_one({"server_id": user.guild.id})
        if server and user.id in server.get("admins", []):
            return True
        return False
    
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)

    @commands.hybrid_command(name="givepoints", description="Give points to a user")
    async def givepoints(self, ctx, user: discord.Member, points: int):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
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

    @commands.hybrid_command(name="checkpoints", description="Check user's points")
    async def checkpoints(self, ctx, user: discord.Member):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
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

    @commands.hybrid_command(name="blacklist", description="Blacklist a user")
    async def blacklist(self, ctx, user: discord.Member, days: int = 30, *, reason: str = "No reason provided"):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        expire_date = datetime.now(timezone.utc) + timedelta(days=days)
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "blacklisted": True,
                    "blacklist_expires": expire_date,
                    "blacklist_reason": reason,
                    "blacklisted_by": ctx.author.id
                }
            },
            upsert=True
        )
        
        embed = discord.Embed(
            title="🚫 User Blacklisted",
            description=f"{user.mention} has been blacklisted",
            color=discord.Color.red()
        )
        embed.add_field(name="Duration", value=f"**{days}** days", inline=True)
        embed.add_field(name="Expires", value=f"<t:{int(expire_date.timestamp())}:R>", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🚫 {ctx.author.mention} blacklisted {user.mention} for {days} days | Reason: {reason}",
            discord.Color.red()
        )

    @commands.hybrid_command(name="unblacklist", description="Remove user from blacklist")
    async def unblacklist(self, ctx, user: discord.Member):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "blacklisted": False,
                    "blacklist_expires": None,
                    "blacklist_reason": None,
                    "blacklisted_by": None
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

    @commands.hybrid_command(name="warn", description="Warn a user")
    async def warn(self, ctx, user: discord.Member, *, reason: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        warning_data = {
            "user_id": user.id,
            "guild_id": ctx.guild.id,
            "moderator_id": ctx.author.id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc)
        }
        
        await self.db.warnings.insert_one(warning_data)
        
        user_warnings = await self.db.warnings.count_documents({
            "user_id": user.id,
            "guild_id": ctx.guild.id
        })
        
        embed = discord.Embed(
            title="⚠️ User Warned",
            description=f"{user.mention} has been warned",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=f"**{user_warnings}**", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        
        await ctx.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="⚠️ You have been warned",
                description=f"You were warned in **{ctx.guild.name}**",
                color=discord.Color.orange()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Total Warnings", value=f"**{user_warnings}**", inline=True)
            await user.send(embed=dm_embed)
        except:
            pass
        
        await self.log_action(
            ctx.guild.id,
            f"⚠️ {ctx.author.mention} warned {user.mention} | Reason: {reason}",
            discord.Color.orange()
        )
        
        if user_warnings >= 3:
            await ctx.send(f"⚠️ {user.mention} has **{user_warnings}** warnings. Consider taking further action.")

    @commands.hybrid_command(name="warnings", description="Check user warnings")
    async def warnings(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.author
        
        warnings = await self.db.warnings.find({
            "user_id": user.id,
            "guild_id": ctx.guild.id
        }).sort("timestamp", -1).limit(10).to_list(None)
        
        if not warnings:
            await ctx.send(f"✅ {user.mention} has no warnings!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⚠️ Warnings for {user.display_name}",
            description=f"Total warnings: **{len(warnings)}**",
            color=discord.Color.orange()
        )
        
        for i, warning in enumerate(warnings[:5], 1):
            moderator = self.bot.get_user(warning["moderator_id"])
            mod_name = moderator.mention if moderator else "Unknown"
            timestamp = warning["timestamp"]
            embed.add_field(
                name=f"Warning #{i}",
                value=f"**Reason:** {warning['reason']}\n**By:** {mod_name}\n**Date:** <t:{int(timestamp.timestamp())}:R>",
                inline=False
            )
        
        if len(warnings) > 5:
            embed.set_footer(text=f"Showing latest 5 of {len(warnings)} warnings")
        
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="clearwarnings", description="Clear all warnings for a user")
    async def clearwarnings(self, ctx, user: discord.Member):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        result = await self.db.warnings.delete_many({
            "user_id": user.id,
            "guild_id": ctx.guild.id
        })
        
        embed = discord.Embed(
            title="✅ Warnings Cleared",
            description=f"Cleared **{result.deleted_count}** warnings for {user.mention}",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🗑️ {ctx.author.mention} cleared {result.deleted_count} warnings for {user.mention}",
            discord.Color.green()
        )

    @commands.hybrid_command(name="kick", description="Kick a user from the server")
    async def kick(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        if user.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot kick someone with equal or higher role!", ephemeral=True)
            return
        
        try:
            await user.send(f"You have been kicked from **{ctx.guild.name}**\nReason: {reason}")
        except:
            pass
        
        await user.kick(reason=f"{ctx.author} - {reason}")
        
        embed = discord.Embed(
            title="👟 User Kicked",
            description=f"{user.mention} has been kicked",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"👟 {ctx.author.mention} kicked {user} | Reason: {reason}",
            discord.Color.orange()
        )

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    async def ban(self, ctx, user: discord.Member, days: int = 0, *, reason: str = "No reason provided"):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        if user.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot ban someone with equal or higher role!", ephemeral=True)
            return
        
        try:
            await user.send(f"You have been banned from **{ctx.guild.name}**\nReason: {reason}")
        except:
            pass
        
        await ctx.guild.ban(user, reason=f"{ctx.author} - {reason}", delete_message_days=days)
        
        embed = discord.Embed(
            title="🔨 User Banned",
            description=f"{user.mention} has been banned",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Messages Deleted", value=f"{days} days", inline=True)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🔨 {ctx.author.mention} banned {user} | Reason: {reason}",
            discord.Color.red()
        )

    @commands.hybrid_command(name="unban", description="Unban a user")
    async def unban(self, ctx, user_id: str, *, reason: str = "No reason provided"):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        try:
            user_id = int(user_id)
        except:
            await ctx.send("❌ Invalid user ID!", ephemeral=True)
            return
        
        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=f"{ctx.author} - {reason}")
            
            embed = discord.Embed(
                title="✅ User Unbanned",
                description=f"User ID `{user_id}` has been unbanned",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"✅ {ctx.author.mention} unbanned user ID {user_id} | Reason: {reason}",
                discord.Color.green()
            )
        except discord.NotFound:
            await ctx.send("❌ User not found in ban list!", ephemeral=True)

    @commands.hybrid_command(name="mute", description="Timeout a user")
    async def mute(self, ctx, user: discord.Member, duration: str, *, reason: str = "No reason provided"):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        if user.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot mute someone with equal or higher role!", ephemeral=True)
            return
        
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = duration[-1].lower()
        
        if unit not in time_units:
            await ctx.send("❌ Invalid duration format! Use: 10s, 5m, 2h, 1d", ephemeral=True)
            return
        
        try:
            amount = int(duration[:-1])
            seconds = amount * time_units[unit]
            
            if seconds > 2419200:
                await ctx.send("❌ Maximum timeout duration is 28 days!", ephemeral=True)
                return
            
            timeout_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            await user.timeout(timeout_until, reason=reason)
            
            embed = discord.Embed(
                title="🔇 User Muted",
                description=f"{user.mention} has been timed out",
                color=discord.Color.orange()
            )
            embed.add_field(name="Duration", value=duration, inline=True)
            embed.add_field(name="Until", value=f"<t:{int(timeout_until.timestamp())}:R>", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"🔇 {ctx.author.mention} muted {user.mention} for {duration} | Reason: {reason}",
                discord.Color.orange()
            )
        except ValueError:
            await ctx.send("❌ Invalid duration format! Use: 10s, 5m, 2h, 1d", ephemeral=True)

    @commands.hybrid_command(name="unmute", description="Remove timeout from a user")
    async def unmute(self, ctx, user: discord.Member):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        await user.timeout(None)
        
        embed = discord.Embed(
            title="🔊 User Unmuted",
            description=f"{user.mention} has been unmuted",
            color=discord.Color.green()
        )
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🔊 {ctx.author.mention} unmuted {user.mention}",
            discord.Color.green()
        )

    @commands.hybrid_command(name="purge", description="Delete multiple messages")
    async def purge(self, ctx, amount: int, user: discord.Member = None):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        if amount < 1 or amount > 100:
            await ctx.send("❌ Amount must be between 1 and 100!", ephemeral=True)
            return
        
        await ctx.defer(ephemeral=True)
        
        def check(msg):
            return user is None or msg.author == user
        
        deleted = await ctx.channel.purge(limit=amount, check=check)
        
        embed = discord.Embed(
            title="🗑️ Messages Purged",
            description=f"Deleted **{len(deleted)}** messages",
            color=discord.Color.blue()
        )
        if user:
            embed.add_field(name="From User", value=user.mention, inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        
        await ctx.send(embed=embed, ephemeral=True)
        
        await self.log_action(
            ctx.guild.id,
            f"🗑️ {ctx.author.mention} purged {len(deleted)} messages" + (f" from {user.mention}" if user else ""),
            discord.Color.blue()
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

    @commands.hybrid_command(name="serverban", description="Ban user from using bot in this server")
    async def serverban(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        await self.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$addToSet": {"banned_users": user.id}}
        )
        
        embed = discord.Embed(
            title="🚫 User Server Banned",
            description=f"{user.mention} can no longer use bot commands in this server",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"🚫 {ctx.author.mention} server-banned {user.mention} | Reason: {reason}",
            discord.Color.red()
        )

    @commands.hybrid_command(name="serverunban", description="Unban user from using bot in this server")
    async def serverunban(self, ctx, user: discord.Member):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ You need admin permissions!", ephemeral=True)
            return
        
        await self.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$pull": {"banned_users": user.id}}
        )
        
        embed = discord.Embed(
            title="✅ User Server Unbanned",
            description=f"{user.mention} can now use bot commands in this server",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"✅ {ctx.author.mention} server-unbanned {user.mention}",
            discord.Color.green()
        )

    @commands.hybrid_command(name="addadmin", description="Add bot admin for this server")
    async def addadmin(self, ctx, user: discord.Member):
        if not ctx.author.guild_permissions.administrator and not await self.is_owner(ctx.author.id):
            await ctx.send("❌ You need administrator permissions!", ephemeral=True)
            return
        
        await self.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$addToSet": {"admins": user.id}}
        )
        
        embed = discord.Embed(
            title="✅ Admin Added",
            description=f"{user.mention} is now a bot admin for this server",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"👮 {ctx.author.mention} added {user.mention} as bot admin",
            discord.Color.green()
        )

    @commands.hybrid_command(name="removeadmin", description="Remove bot admin from this server")
    async def removeadmin(self, ctx, user: discord.Member):
        if not ctx.author.guild_permissions.administrator and not await self.is_owner(ctx.author.id):
            await ctx.send("❌ You need administrator permissions!", ephemeral=True)
            return
        
        await self.db.servers.update_one(
            {"server_id": ctx.guild.id},
            {"$pull": {"admins": user.id}}
        )
        
        embed = discord.Embed(
            title="✅ Admin Removed",
            description=f"{user.mention} is no longer a bot admin for this server",
            color=discord.Color.orange()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"👮 {ctx.author.mention} removed {user.mention} as bot admin",
            discord.Color.orange()
        )

async def setup(bot):
    await bot.add_cog(AdminModerationCog(bot))