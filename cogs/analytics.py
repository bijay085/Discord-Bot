# cogs/analytics.py
# Location: cogs/analytics.py
# Description: Analytics tracking with batch processing and performance optimization

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
from collections import defaultdict

class AnalyticsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.update_analytics.start()
        self.command_cache = defaultdict(int)
        self.user_cache = set()
        self._command_batch = []
        self._max_batch_size = 50
        
    async def cog_unload(self):
        self.update_analytics.cancel()
        await self.flush_cache()
        await self.flush_command_batch()
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    async def track_command(self, command_name: str, user_id: int, guild_id: int):
        # Add to local cache for quick stats
        self.command_cache[command_name] += 1
        self.user_cache.add(user_id)
        
        # Batch database updates for better performance
        self._command_batch.append({
            "command": command_name,
            "user_id": user_id,
            "guild_id": guild_id,
            "timestamp": datetime.now(timezone.utc)
        })
        
        if len(self._command_batch) >= self._max_batch_size:
            await self.flush_command_batch()
    
    async def flush_command_batch(self):
        if not self._command_batch:
            return
            
        try:
            # Group by command for bulk updates
            command_groups = defaultdict(list)
            for item in self._command_batch:
                command_groups[item["command"]].append(item)
            
            # Bulk update for each command
            for command_name, items in command_groups.items():
                user_ids = list(set(item["user_id"] for item in items))
                guild_ids = list(set(item["guild_id"] for item in items))
                count = len(items)
                
                await self.db.analytics.update_one(
                    {"_id": "command_usage"},
                    {
                        "$inc": {
                            f"commands.{command_name}.total": count,
                            f"commands.{command_name}.today": count,
                            f"commands.{command_name}.this_week": count,
                            f"commands.{command_name}.this_month": count
                        },
                        "$addToSet": {
                            f"commands.{command_name}.unique_users": {"$each": user_ids},
                            f"commands.{command_name}.guilds": {"$each": guild_ids}
                        }
                    },
                    upsert=True
                )
            
            # Insert analytics entries
            if self._command_batch:
                await self.db.analytics.insert_many(
                    [
                        {
                            "type": "command_usage",
                            "command": item["command"],
                            "user_id": item["user_id"],
                            "guild_id": item["guild_id"],
                            "timestamp": item["timestamp"]
                        }
                        for item in self._command_batch
                    ]
                )
            
            self._command_batch.clear()
            
        except Exception as e:
            print(f"Error flushing command batch: {e}")
    
    async def track_cookie_extraction(self, cookie_type: str, user_id: int, file_name: str):
        await self.db.analytics.update_one(
            {"_id": "cookie_extractions"},
            {
                "$inc": {
                    f"cookies.{cookie_type}.total": 1,
                    f"cookies.{cookie_type}.today": 1,
                    f"cookies.{cookie_type}.this_week": 1,
                    f"cookies.{cookie_type}.this_month": 1,
                    "total_all_time": 1,
                    "total_today": 1,
                    "total_this_week": 1,
                    "total_this_month": 1
                },
                "$addToSet": {
                    f"cookies.{cookie_type}.unique_users": user_id,
                    f"cookies.{cookie_type}.files": file_name
                },
                "$set": {
                    "last_updated": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
    
    async def track_active_user(self, user_id: int, username: str):
        await self.db.analytics.update_one(
            {"_id": "active_users"},
            {
                "$addToSet": {
                    "all_time_users": user_id,
                    "daily_active_users": user_id,
                    "weekly_active_users": user_id,
                    "monthly_active_users": user_id
                },
                "$set": {
                    f"user_details.{user_id}": {
                        "username": username,
                        "last_seen": datetime.now(timezone.utc)
                    }
                }
            },
            upsert=True
        )
    
    async def flush_cache(self):
        if self.command_cache:
            for command, count in self.command_cache.items():
                await self.db.analytics.update_one(
                    {"_id": "real_time_stats"},
                    {"$inc": {f"commands.{command}": count}},
                    upsert=True
                )
            self.command_cache.clear()
        
        if self.user_cache:
            await self.db.analytics.update_one(
                {"_id": "real_time_stats"},
                {"$addToSet": {"active_users": {"$each": list(self.user_cache)}}},
                upsert=True
            )
            self.user_cache.clear()
    
    @tasks.loop(minutes=5)
    async def update_analytics(self):
        try:
            await self.flush_cache()
            await self.flush_command_batch()
            
            analytics_data = await self.db.analytics.find_one({"_id": "bot_analytics"})
            if not analytics_data:
                analytics_data = {
                    "_id": "bot_analytics",
                    "total_users": 0,
                    "total_servers": 0,
                    "total_commands": 0,
                    "total_cookies": 0,
                    "last_updated": datetime.now(timezone.utc)
                }
            
            total_users = await self.db.users.count_documents({})
            total_servers = await self.db.servers.count_documents({})
            
            total_commands = 0
            command_usage = await self.db.analytics.find_one({"_id": "command_usage"})
            if command_usage and command_usage.get("commands"):
                for cmd_data in command_usage["commands"].values():
                    total_commands += cmd_data.get("total", 0)
            
            total_cookies = 0
            cookie_data = await self.db.analytics.find_one({"_id": "cookie_extractions"})
            if cookie_data:
                total_cookies = cookie_data.get("total_all_time", 0)
            
            await self.db.analytics.update_one(
                {"_id": "bot_analytics"},
                {
                    "$set": {
                        "total_users": total_users,
                        "total_servers": total_servers,
                        "total_commands": total_commands,
                        "total_cookies": total_cookies,
                        "last_updated": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
            
            now = datetime.now(timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=now.weekday())
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            if now.hour == 0 and now.minute < 5:
                await self.reset_daily_stats()
            
            if now.weekday() == 0 and now.hour == 0 and now.minute < 5:
                await self.reset_weekly_stats()
            
            if now.day == 1 and now.hour == 0 and now.minute < 5:
                await self.reset_monthly_stats()
                
        except Exception as e:
            print(f"Error in analytics update: {e}")
    
    async def reset_daily_stats(self):
        await self.db.analytics.update_one(
            {"_id": "command_usage"},
            {"$set": {f"commands.{cmd}.today": 0 for cmd in ["cookie", "daily", "points", "help", "stock", "feedback", "invites", "status"]}},
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "cookie_extractions"},
            {
                "$set": {
                    "total_today": 0,
                    **{f"cookies.{cookie}.today": 0 for cookie in ["netflix", "spotify", "prime", "jiohotstar", "tradingview", "chatgpt", "claude", "peacock", "crunchyroll", "canalplus"]}
                }
            },
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "active_users"},
            {"$set": {"daily_active_users": []}},
            upsert=True
        )
    
    async def reset_weekly_stats(self):
        await self.db.analytics.update_one(
            {"_id": "command_usage"},
            {"$set": {f"commands.{cmd}.this_week": 0 for cmd in ["cookie", "daily", "points", "help", "stock", "feedback", "invites", "status"]}},
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "cookie_extractions"},
            {
                "$set": {
                    "total_this_week": 0,
                    **{f"cookies.{cookie}.this_week": 0 for cookie in ["netflix", "spotify", "prime", "jiohotstar", "tradingview", "chatgpt", "claude", "peacock", "crunchyroll", "canalplus"]}
                }
            },
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "active_users"},
            {"$set": {"weekly_active_users": []}},
            upsert=True
        )
    
    async def reset_monthly_stats(self):
        await self.db.analytics.update_one(
            {"_id": "command_usage"},
            {"$set": {f"commands.{cmd}.this_month": 0 for cmd in ["cookie", "daily", "points", "help", "stock", "feedback", "invites", "status"]}},
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "cookie_extractions"},
            {
                "$set": {
                    "total_this_month": 0,
                    **{f"cookies.{cookie}.this_month": 0 for cookie in ["netflix", "spotify", "prime", "jiohotstar", "tradingview", "chatgpt", "claude", "peacock", "crunchyroll", "canalplus"]}
                }
            },
            upsert=True
        )
        
        await self.db.analytics.update_one(
            {"_id": "active_users"},
            {"$set": {"monthly_active_users": []}},
            upsert=True
        )
    
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if not ctx.command:
            return
        
        await self.track_command(ctx.command.name, ctx.author.id, ctx.guild.id)
        await self.track_active_user(ctx.author.id, str(ctx.author))
    
    @commands.hybrid_command(name="analytics", description="View detailed bot analytics (Owner only)")
    async def analytics(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        # Flush pending data before showing analytics
        await self.flush_cache()
        await self.flush_command_batch()
        
        analytics = await self.db.analytics.find_one({"_id": "bot_analytics"})
        active_users = await self.db.analytics.find_one({"_id": "active_users"})
        command_usage = await self.db.analytics.find_one({"_id": "command_usage"})
        cookie_extractions = await self.db.analytics.find_one({"_id": "cookie_extractions"})
        
        embed = discord.Embed(
            title="📊 Complete Bot Analytics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if analytics:
            embed.add_field(
                name="📈 Overall Statistics",
                value=f"**Total Users:** {analytics.get('total_users', 0):,}\n"
                      f"**Total Servers:** {analytics.get('total_servers', 0):,}\n"
                      f"**Total Commands:** {analytics.get('total_commands', 0):,}\n"
                      f"**Total Cookies:** {analytics.get('total_cookies', 0):,}",
                inline=False
            )
        
        if active_users:
            all_time = len(active_users.get("all_time_users", []))
            daily = len(active_users.get("daily_active_users", []))
            weekly = len(active_users.get("weekly_active_users", []))
            monthly = len(active_users.get("monthly_active_users", []))
            
            embed.add_field(
                name="👥 Active Users",
                value=f"**All Time:** {all_time:,}\n"
                      f"**Today:** {daily:,}\n"
                      f"**This Week:** {weekly:,}\n"
                      f"**This Month:** {monthly:,}",
                inline=True
            )
        
        if cookie_extractions:
            embed.add_field(
                name="🍪 Cookie Extractions",
                value=f"**All Time:** {cookie_extractions.get('total_all_time', 0):,}\n"
                      f"**Today:** {cookie_extractions.get('total_today', 0):,}\n"
                      f"**This Week:** {cookie_extractions.get('total_this_week', 0):,}\n"
                      f"**This Month:** {cookie_extractions.get('total_this_month', 0):,}",
                inline=True
            )
        
        if command_usage and command_usage.get("commands"):
            top_commands = []
            for cmd, data in command_usage["commands"].items():
                total = data.get("total", 0)
                if total > 0:
                    top_commands.append((cmd, total))
            
            top_commands.sort(key=lambda x: x[1], reverse=True)
            if top_commands:
                cmd_text = "\n".join([f"**{cmd}:** {count:,}" for cmd, count in top_commands[:5]])
                embed.add_field(
                    name="🎯 Top Commands",
                    value=cmd_text,
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="cookiestats", description="View detailed cookie statistics (Owner only)")
    async def cookiestats(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        cookie_data = await self.db.analytics.find_one({"_id": "cookie_extractions"})
        
        embed = discord.Embed(
            title="🍪 Detailed Cookie Statistics",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if cookie_data and cookie_data.get("cookies"):
            for cookie_type, data in cookie_data["cookies"].items():
                total = data.get("total", 0)
                today = data.get("today", 0)
                week = data.get("this_week", 0)
                unique_users = len(data.get("unique_users", []))
                
                embed.add_field(
                    name=f"🍪 {cookie_type.title()}",
                    value=f"**Total:** {total:,}\n"
                          f"**Today:** {today}\n"
                          f"**Week:** {week}\n"
                          f"**Users:** {unique_users}",
                    inline=True
                )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="userstats", description="View detailed user statistics (Owner only)")
    async def userstats(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "avg_points": {"$avg": "$points"},
                    "total_points": {"$sum": "$points"},
                    "avg_claims": {"$avg": "$total_claims"},
                    "total_claims": {"$sum": "$total_claims"},
                    "avg_trust": {"$avg": "$trust_score"},
                    "blacklisted": {"$sum": {"$cond": ["$blacklisted", 1, 0]}}
                }
            }
        ]
        
        stats = await self.db.users.aggregate(pipeline).to_list(1)
        
        embed = discord.Embed(
            title="👥 User Statistics",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if stats:
            data = stats[0]
            embed.add_field(
                name="💰 Points",
                value=f"**Total:** {data.get('total_points', 0):,}\n"
                      f"**Average:** {data.get('avg_points', 0):.1f}",
                inline=True
            )
            embed.add_field(
                name="🍪 Claims",
                value=f"**Total:** {data.get('total_claims', 0):,}\n"
                      f"**Average:** {data.get('avg_claims', 0):.1f}",
                inline=True
            )
            embed.add_field(
                name="📊 Other",
                value=f"**Avg Trust:** {data.get('avg_trust', 0):.1f}\n"
                      f"**Blacklisted:** {data.get('blacklisted', 0)}",
                inline=True
            )
        
        top_users = await self.db.users.find().sort("total_claims", -1).limit(5).to_list(5)
        if top_users:
            user_text = []
            for i, user in enumerate(top_users, 1):
                user_text.append(f"{i}. <@{user['user_id']}>: **{user.get('total_claims', 0)}** claims")
            embed.add_field(
                name="🏆 Top Cookie Claimers",
                value="\n".join(user_text),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="serverstats", description="View server statistics (Owner only)")
    async def serverstats(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        total_servers = await self.db.servers.count_documents({})
        enabled_servers = await self.db.servers.count_documents({"enabled": True})
        
        pipeline = [
            {"$unwind": "$cookies"},
            {"$group": {
                "_id": None,
                "total_cookie_types": {"$sum": 1}
            }}
        ]
        
        embed = discord.Embed(
            title="🏠 Server Statistics",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Overview",
            value=f"**Total Servers:** {total_servers}\n"
                  f"**Enabled:** {enabled_servers}\n"
                  f"**Disabled:** {total_servers - enabled_servers}",
            inline=False
        )
        
        active_in_bot = len(self.bot.guilds)
        embed.add_field(
            name="🤖 Bot Status",
            value=f"**Active Servers:** {active_in_bot}\n"
                  f"**Database Only:** {total_servers - active_in_bot}",
            inline=True
        )
        
        command_data = await self.db.analytics.find_one({"_id": "command_usage"})
        if command_data and command_data.get("commands"):
            total_guilds = set()
            for cmd_data in command_data["commands"].values():
                guilds = cmd_data.get("guilds", [])
                total_guilds.update(guilds)
            
            embed.add_field(
                name="💬 Activity",
                value=f"**Active Servers:** {len(total_guilds)}\n"
                      f"**Inactive:** {active_in_bot - len(total_guilds)}",
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="trends", description="View usage trends (Owner only)")
    async def trends(self, ctx, period: str = "week"):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        valid_periods = ["day", "week", "month"]
        if period not in valid_periods:
            await ctx.send(f"❌ Invalid period! Use: {', '.join(valid_periods)}", ephemeral=True)
            return
        
        command_data = await self.db.analytics.find_one({"_id": "command_usage"})
        cookie_data = await self.db.analytics.find_one({"_id": "cookie_extractions"})
        
        embed = discord.Embed(
            title=f"📈 {period.title()} Trends",
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc)
        )
        
        period_key = {"day": "today", "week": "this_week", "month": "this_month"}[period]
        
        if command_data and command_data.get("commands"):
            cmd_trends = []
            for cmd, data in command_data["commands"].items():
                count = data.get(period_key, 0)
                if count > 0:
                    cmd_trends.append((cmd, count))
            
            cmd_trends.sort(key=lambda x: x[1], reverse=True)
            if cmd_trends:
                trend_text = "\n".join([f"**{cmd}:** {count}" for cmd, count in cmd_trends[:5]])
                embed.add_field(
                    name=f"🎯 Top Commands ({period})",
                    value=trend_text,
                    inline=False
                )
        
        if cookie_data and cookie_data.get("cookies"):
            cookie_trends = []
            for cookie, data in cookie_data["cookies"].items():
                count = data.get(period_key, 0)
                if count > 0:
                    cookie_trends.append((cookie, count))
            
            cookie_trends.sort(key=lambda x: x[1], reverse=True)
            if cookie_trends:
                cookie_text = "\n".join([f"**{cookie}:** {count}" for cookie, count in cookie_trends[:5]])
                embed.add_field(
                    name=f"🍪 Top Cookies ({period})",
                    value=cookie_text,
                    inline=False
                )
        
        embed.add_field(
            name="📊 Total Activity",
            value=f"**Commands:** {sum(c[1] for c in cmd_trends) if 'cmd_trends' in locals() else 0}\n"
                  f"**Cookies:** {cookie_data.get(f'total_{period_key}', 0) if cookie_data else 0}",
            inline=False
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AnalyticsCog(bot))