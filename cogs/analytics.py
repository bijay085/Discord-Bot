# cogs/analytics.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import asyncio

class AnalyticsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.update_analytics.start()
        
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def track_command(self, command_name: str, user_id: int, guild_id: int):
        now = datetime.now(timezone.utc)
        
        await self.db.analytics.update_one(
            {"_id": "command_stats"},
            {
                "$inc": {
                    f"commands.{command_name}.total": 1,
                    f"commands.{command_name}.today": 1,
                    f"commands.{command_name}.this_week": 1,
                    f"commands.{command_name}.this_month": 1,
                    "total_commands": 1,
                    "commands_today": 1,
                    "commands_this_week": 1,
                    "commands_this_month": 1
                },
                "$addToSet": {
                    f"commands.{command_name}.unique_users": user_id,
                    f"commands.{command_name}.servers": guild_id
                },
                "$set": {
                    f"commands.{command_name}.last_used": now,
                    "last_command": {
                        "name": command_name,
                        "user_id": user_id,
                        "guild_id": guild_id,
                        "time": now
                    }
                }
            },
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": f"daily_{now.strftime('%Y-%m-%d')}"},
            {
                "$inc": {
                    f"commands.{command_name}": 1,
                    "total_commands": 1
                },
                "$addToSet": {
                    "active_users": user_id,
                    "active_guilds": guild_id
                }
            },
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "user_activity"},
            {
                "$addToSet": {
                    "all_time_users": user_id,
                    "daily_active_users": user_id,
                    "weekly_active_users": user_id,
                    "monthly_active_users": user_id
                },
                "$set": {
                    f"last_seen.{user_id}": now
                }
            },
            upsert=True
        )
    
    async def track_cookie_claim(self, cookie_type: str, user_id: int, guild_id: int, file_name: str):
        now = datetime.now(timezone.utc)
        
        await self.db.analytics.update_one(
            {"_id": "cookie_stats"},
            {
                "$inc": {
                    f"cookies.{cookie_type}.total": 1,
                    f"cookies.{cookie_type}.today": 1,
                    f"cookies.{cookie_type}.this_week": 1,
                    f"cookies.{cookie_type}.this_month": 1,
                    "total_cookies_claimed": 1,
                    "cookies_today": 1,
                    "cookies_this_week": 1,
                    "cookies_this_month": 1
                },
                "$addToSet": {
                    f"cookies.{cookie_type}.unique_users": user_id,
                    f"cookies.{cookie_type}.servers": guild_id,
                    f"cookies.{cookie_type}.files_used": file_name
                },
                "$set": {
                    f"cookies.{cookie_type}.last_claimed": now
                }
            },
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": f"daily_{now.strftime('%Y-%m-%d')}"},
            {
                "$inc": {
                    f"cookies.{cookie_type}": 1,
                    "total_cookies": 1
                }
            },
            upsert=True
        )
    
    @tasks.loop(hours=1)
    async def update_analytics(self):
        try:
            now = datetime.now(timezone.utc)
            
            if now.hour == 0:
                await self.db.analytics.update_one(
                    {"_id": "command_stats"},
                    {
                        "$set": {
                            "commands_today": 0
                        },
                        "$unset": {
                            f"commands.$[].today": ""
                        }
                    }
                )
                
                await self.db.analytics.update_one(
                    {"_id": "cookie_stats"},
                    {
                        "$set": {
                            "cookies_today": 0
                        },
                        "$unset": {
                            f"cookies.$[].today": ""
                        }
                    }
                )
                
                await self.db.analytics.update_one(
                    {"_id": "user_activity"},
                    {
                        "$set": {
                            "daily_active_users": []
                        }
                    }
                )
            
            if now.weekday() == 0 and now.hour == 0:
                await self.db.analytics.update_one(
                    {"_id": "command_stats"},
                    {
                        "$set": {
                            "commands_this_week": 0
                        },
                        "$unset": {
                            f"commands.$[].this_week": ""
                        }
                    }
                )
                
                await self.db.analytics.update_one(
                    {"_id": "cookie_stats"},
                    {
                        "$set": {
                            "cookies_this_week": 0
                        },
                        "$unset": {
                            f"cookies.$[].this_week": ""
                        }
                    }
                )
                
                await self.db.analytics.update_one(
                    {"_id": "user_activity"},
                    {
                        "$set": {
                            "weekly_active_users": []
                        }
                    }
                )
            
            if now.day == 1 and now.hour == 0:
                await self.db.analytics.update_one(
                    {"_id": "command_stats"},
                    {
                        "$set": {
                            "commands_this_month": 0
                        },
                        "$unset": {
                            f"commands.$[].this_month": ""
                        }
                    }
                )
                
                await self.db.analytics.update_one(
                    {"_id": "cookie_stats"},
                    {
                        "$set": {
                            "cookies_this_month": 0
                        },
                        "$unset": {
                            f"cookies.$[].this_month": ""
                        }
                    }
                )
                
                await self.db.analytics.update_one(
                    {"_id": "user_activity"},
                    {
                        "$set": {
                            "monthly_active_users": []
                        }
                    }
                )
                
        except Exception as e:
            print(f"Error in analytics update: {e}")
    
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if not ctx.command:
            return
        
        await self.track_command(
            ctx.command.name,
            ctx.author.id,
            ctx.guild.id if ctx.guild else 0
        )
    
    @commands.hybrid_command(name="analytics", description="View bot analytics (Owner only)")
    async def analytics(self, ctx, category: str = "overview"):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        if category == "overview":
            await self.send_overview_analytics(ctx)
        elif category == "commands":
            await self.send_command_analytics(ctx)
        elif category == "cookies":
            await self.send_cookie_analytics(ctx)
        elif category == "users":
            await self.send_user_analytics(ctx)
        elif category == "servers":
            await self.send_server_analytics(ctx)
        else:
            embed = discord.Embed(
                title="📊 Analytics Categories",
                description="Use `/analytics <category>` to view specific stats",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Available Categories",
                value=(
                    "• `overview` - General statistics\n"
                    "• `commands` - Command usage stats\n"
                    "• `cookies` - Cookie claim stats\n"
                    "• `users` - User activity stats\n"
                    "• `servers` - Server statistics"
                ),
                inline=False
            )
            await ctx.send(embed=embed)
    
    async def send_overview_analytics(self, ctx):
        command_stats = await self.db.analytics.find_one({"_id": "command_stats"}) or {}
        cookie_stats = await self.db.analytics.find_one({"_id": "cookie_stats"}) or {}
        user_activity = await self.db.analytics.find_one({"_id": "user_activity"}) or {}
        
        total_users = await self.db.users.count_documents({})
        active_users = len(user_activity.get("all_time_users", []))
        daily_active = len(user_activity.get("daily_active_users", []))
        weekly_active = len(user_activity.get("weekly_active_users", []))
        monthly_active = len(user_activity.get("monthly_active_users", []))
        
        total_servers = await self.db.servers.count_documents({})
        active_servers = len(self.bot.guilds)
        
        embed = discord.Embed(
            title="📊 Bot Analytics Overview",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="👥 User Statistics",
            value=(
                f"Total Registered: **{total_users}**\n"
                f"All-Time Active: **{active_users}**\n"
                f"Daily Active: **{daily_active}**\n"
                f"Weekly Active: **{weekly_active}**\n"
                f"Monthly Active: **{monthly_active}**"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🏢 Server Statistics",
            value=(
                f"Total Servers: **{total_servers}**\n"
                f"Active Servers: **{active_servers}**\n"
                f"Total Members: **{sum(g.member_count for g in self.bot.guilds)}**"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📈 Command Usage",
            value=(
                f"Total Commands: **{command_stats.get('total_commands', 0)}**\n"
                f"Today: **{command_stats.get('commands_today', 0)}**\n"
                f"This Week: **{command_stats.get('commands_this_week', 0)}**\n"
                f"This Month: **{command_stats.get('commands_this_month', 0)}**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🍪 Cookie Claims",
            value=(
                f"Total Claims: **{cookie_stats.get('total_cookies_claimed', 0)}**\n"
                f"Today: **{cookie_stats.get('cookies_today', 0)}**\n"
                f"This Week: **{cookie_stats.get('cookies_this_week', 0)}**\n"
                f"This Month: **{cookie_stats.get('cookies_this_month', 0)}**"
            ),
            inline=False
        )
        
        if command_stats.get("last_command"):
            last_cmd = command_stats["last_command"]
            embed.add_field(
                name="🕐 Last Command",
                value=(
                    f"Command: `/{last_cmd.get('name', 'Unknown')}`\n"
                    f"User: <@{last_cmd.get('user_id', 0)}>\n"
                    f"Time: <t:{int(last_cmd.get('time', datetime.now(timezone.utc)).timestamp())}:R>"
                ),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    async def send_command_analytics(self, ctx):
        command_stats = await self.db.analytics.find_one({"_id": "command_stats"}) or {}
        commands = command_stats.get("commands", {})
        
        embed = discord.Embed(
            title="📊 Command Usage Analytics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        sorted_commands = sorted(
            commands.items(),
            key=lambda x: x[1].get("total", 0),
            reverse=True
        )[:10]
        
        if sorted_commands:
            command_text = []
            for cmd_name, cmd_data in sorted_commands:
                total = cmd_data.get("total", 0)
                today = cmd_data.get("today", 0)
                unique_users = len(cmd_data.get("unique_users", []))
                command_text.append(
                    f"**/{cmd_name}**\n"
                    f"Total: {total} | Today: {today} | Users: {unique_users}"
                )
            
            embed.add_field(
                name="🏆 Top 10 Commands",
                value="\n\n".join(command_text),
                inline=False
            )
        
        embed.add_field(
            name="📈 Total Statistics",
            value=(
                f"Total Commands Used: **{command_stats.get('total_commands', 0)}**\n"
                f"Unique Commands: **{len(commands)}**\n"
                f"Commands Today: **{command_stats.get('commands_today', 0)}**"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    async def send_cookie_analytics(self, ctx):
        cookie_stats = await self.db.analytics.find_one({"_id": "cookie_stats"}) or {}
        cookies = cookie_stats.get("cookies", {})
        
        embed = discord.Embed(
            title="🍪 Cookie Claim Analytics",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        sorted_cookies = sorted(
            cookies.items(),
            key=lambda x: x[1].get("total", 0),
            reverse=True
        )
        
        if sorted_cookies:
            cookie_text = []
            for cookie_type, cookie_data in sorted_cookies:
                total = cookie_data.get("total", 0)
                today = cookie_data.get("today", 0)
                unique_users = len(cookie_data.get("unique_users", []))
                unique_files = len(cookie_data.get("files_used", []))
                
                cookie_text.append(
                    f"**{cookie_type.upper()}**\n"
                    f"Total: {total} | Today: {today}\n"
                    f"Users: {unique_users} | Files: {unique_files}"
                )
            
            for i in range(0, len(cookie_text), 5):
                field_name = "🍪 Cookie Types" if i == 0 else "🍪 More Types"
                embed.add_field(
                    name=field_name,
                    value="\n\n".join(cookie_text[i:i+5]),
                    inline=False
                )
        
        embed.add_field(
            name="📊 Overall Cookie Stats",
            value=(
                f"Total Cookies Claimed: **{cookie_stats.get('total_cookies_claimed', 0)}**\n"
                f"Cookies Today: **{cookie_stats.get('cookies_today', 0)}**\n"
                f"This Week: **{cookie_stats.get('cookies_this_week', 0)}**\n"
                f"This Month: **{cookie_stats.get('cookies_this_month', 0)}**"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    async def send_user_analytics(self, ctx):
        user_activity = await self.db.analytics.find_one({"_id": "user_activity"}) or {}
        
        all_time_users = user_activity.get("all_time_users", [])
        daily_active = user_activity.get("daily_active_users", [])
        weekly_active = user_activity.get("weekly_active_users", [])
        monthly_active = user_activity.get("monthly_active_users", [])
        
        top_users = await self.db.users.find().sort("total_claims", -1).limit(10).to_list(10)
        rich_users = await self.db.users.find().sort("points", -1).limit(10).to_list(10)
        
        embed = discord.Embed(
            title="👥 User Activity Analytics",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Activity Overview",
            value=(
                f"All-Time Users: **{len(all_time_users)}**\n"
                f"Daily Active: **{len(daily_active)}**\n"
                f"Weekly Active: **{len(weekly_active)}**\n"
                f"Monthly Active: **{len(monthly_active)}**"
            ),
            inline=False
        )
        
        if top_users:
            top_text = []
            for i, user in enumerate(top_users[:5], 1):
                top_text.append(
                    f"{i}. <@{user['user_id']}> - **{user.get('total_claims', 0)}** claims"
                )
            embed.add_field(
                name="🏆 Top Claimers",
                value="\n".join(top_text),
                inline=True
            )
        
        if rich_users:
            rich_text = []
            for i, user in enumerate(rich_users[:5], 1):
                rich_text.append(
                    f"{i}. <@{user['user_id']}> - **{user.get('points', 0)}** points"
                )
            embed.add_field(
                name="💰 Richest Users",
                value="\n".join(rich_text),
                inline=True
            )
        
        blacklisted_count = await self.db.users.count_documents({"blacklisted": True})
        embed.add_field(
            name="🚫 Blacklisted Users",
            value=f"**{blacklisted_count}** users",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    async def send_server_analytics(self, ctx):
        total_servers = await self.db.servers.count_documents({})
        enabled_servers = await self.db.servers.count_documents({"enabled": True})
        
        server_claims = defaultdict(int)
        cookie_stats = await self.db.analytics.find_one({"_id": "cookie_stats"}) or {}
        
        for cookie_type, data in cookie_stats.get("cookies", {}).items():
            for server_id in data.get("servers", []):
                server_claims[server_id] += data.get("total", 0)
        
        top_servers = sorted(server_claims.items(), key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(
            title="🏢 Server Analytics",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Server Overview",
            value=(
                f"Total Servers: **{total_servers}**\n"
                f"Active Servers: **{len(self.bot.guilds)}**\n"
                f"Enabled Servers: **{enabled_servers}**\n"
                f"Total Members: **{sum(g.member_count for g in self.bot.guilds)}**"
            ),
            inline=False
        )
        
        if top_servers:
            server_text = []
            for server_id, claims in top_servers[:5]:
                guild = self.bot.get_guild(server_id)
                if guild:
                    server_text.append(f"**{guild.name}** - {claims} claims")
                else:
                    server_text.append(f"Unknown Server ({server_id}) - {claims} claims")
            
            embed.add_field(
                name="🏆 Most Active Servers",
                value="\n".join(server_text),
                inline=False
            )
        
        large_servers = [g for g in self.bot.guilds if g.member_count > 1000]
        if large_servers:
            embed.add_field(
                name="🌟 Large Servers",
                value=(
                    f"Servers with 1000+ members: **{len(large_servers)}**\n"
                    f"Largest: **{max(large_servers, key=lambda g: g.member_count).name}** "
                    f"({max(g.member_count for g in large_servers)} members)"
                ),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="userstats", description="View detailed user statistics (Owner only)")
    async def userstats(self, ctx, user: discord.User):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        user_data = await self.db.users.find_one({"user_id": user.id})
        if not user_data:
            await ctx.send("❌ User not found in database!", ephemeral=True)
            return
        
        command_stats = await self.db.analytics.find_one({"_id": "command_stats"}) or {}
        cookie_stats = await self.db.analytics.find_one({"_id": "cookie_stats"}) or {}
        
        user_commands = 0
        for cmd_name, cmd_data in command_stats.get("commands", {}).items():
            if user.id in cmd_data.get("unique_users", []):
                user_commands += 1
        
        user_cookie_types = 0
        for cookie_type, cookie_data in cookie_stats.get("cookies", {}).items():
            if user.id in cookie_data.get("unique_users", []):
                user_cookie_types += 1
        
        embed = discord.Embed(
            title=f"📊 Detailed Stats: {user.name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(
            name="💰 Economy Stats",
            value=(
                f"Current Points: **{user_data.get('points', 0)}**\n"
                f"Total Earned: **{user_data.get('total_earned', 0)}**\n"
                f"Total Spent: **{user_data.get('total_spent', 0)}**\n"
                f"Trust Score: **{user_data.get('trust_score', 50)}/100**"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🍪 Cookie Stats",
            value=(
                f"Total Claims: **{user_data.get('total_claims', 0)}**\n"
                f"Weekly Claims: **{user_data.get('weekly_claims', 0)}**\n"
                f"Cookie Types Used: **{user_cookie_types}**\n"
                f"Invites: **{user_data.get('invite_count', 0)}**"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📈 Activity",
            value=(
                f"Commands Used: **{user_commands}**\n"
                f"Account Created: <t:{int(user_data.get('account_created', datetime.now(timezone.utc)).timestamp())}:R>\n"
                f"Last Active: <t:{int(user_data.get('last_active', datetime.now(timezone.utc)).timestamp())}:R>"
            ),
            inline=False
        )
        
        if user_data.get("cookie_claims"):
            fav_cookies = sorted(user_data["cookie_claims"].items(), key=lambda x: x[1], reverse=True)[:3]
            if fav_cookies:
                fav_text = "\n".join([f"• {cookie}: **{count}** claims" for cookie, count in fav_cookies])
                embed.add_field(name="🏆 Favorite Cookies", value=fav_text, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="clearanalytics", description="Clear analytics data (Owner only)")
    async def clearanalytics(self, ctx, category: str):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        if category == "daily":
            await self.db.analytics.delete_many({"_id": {"$regex": "^daily_"}})
            await ctx.send("✅ Cleared all daily analytics data!")
        elif category == "commands":
            await self.db.analytics.delete_one({"_id": "command_stats"})
            await ctx.send("✅ Cleared command statistics!")
        elif category == "cookies":
            await self.db.analytics.delete_one({"_id": "cookie_stats"})
            await ctx.send("✅ Cleared cookie statistics!")
        elif category == "users":
            await self.db.analytics.delete_one({"_id": "user_activity"})
            await ctx.send("✅ Cleared user activity data!")
        elif category == "all":
            await self.db.analytics.delete_many({})
            await ctx.send("✅ Cleared ALL analytics data!")
        else:
            await ctx.send("❌ Invalid category! Use: daily, commands, cookies, users, or all", ephemeral=True)
        
        await self.log_action(
            ctx.guild.id,
            f"🗑️ {ctx.author.mention} cleared {category} analytics",
            discord.Color.orange()
        )

async def setup(bot):
    await bot.add_cog(AnalyticsCog(bot))