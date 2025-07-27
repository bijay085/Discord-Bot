# cogs/analytics.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
from typing import Optional, Dict, List
import io
import json

class AnalyticsView(discord.ui.View):
    def __init__(self, data_types: list):
        super().__init__(timeout=180)
        self.selected_type = None
        
        options = []
        emojis = {
            "overview": "📊", "cookies": "🍪", "users": "👥",
            "economy": "💰", "server": "🏠", "trends": "📈"
        }
        
        for data_type in data_types:
            options.append(
                discord.SelectOption(
                    label=data_type.title(),
                    value=data_type,
                    emoji=emojis.get(data_type, "📊")
                )
            )
        
        self.select = discord.ui.Select(
            placeholder="Select analytics type...",
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
    async def select_callback(self, interaction: discord.Interaction):
        self.selected_type = self.select.values[0]
        await interaction.response.defer()

class AnalyticsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.collect_analytics.start()
        self.generate_reports.start()
        
    def cog_unload(self):
        self.collect_analytics.cancel()
        self.generate_reports.cancel()
        
    @tasks.loop(minutes=30)
    async def collect_analytics(self):
        try:
            now = datetime.now(timezone.utc)
            
            total_users = await self.db.users.count_documents({})
            active_users = await self.db.users.count_documents({
                "last_active": {"$gte": now - timedelta(days=7)}
            })
            
            total_claims = await self.db.users.aggregate([
                {"$group": {"_id": None, "total": {"$sum": "$total_claims"}}}
            ]).to_list(1)
            
            total_points = await self.db.users.aggregate([
                {"$group": {"_id": None, "total": {"$sum": "$points"}}}
            ]).to_list(1)
            
            analytics_data = {
                "timestamp": now,
                "users": {
                    "total": total_users,
                    "active_weekly": active_users,
                    "new_today": await self.db.users.count_documents({
                        "account_created": {"$gte": now - timedelta(days=1)}
                    })
                },
                "economy": {
                    "total_points": total_points[0]["total"] if total_points else 0,
                    "total_claims": total_claims[0]["total"] if total_claims else 0,
                    "average_balance": (total_points[0]["total"] / total_users) if total_users > 0 and total_points else 0
                },
                "servers": {
                    "total": len(self.bot.guilds),
                    "members": sum(g.member_count for g in self.bot.guilds)
                }
            }
            
            await self.db.analytics.insert_one(analytics_data)
            
        except Exception as e:
            self.bot.logger.error(f"Error collecting analytics: {e}")
    
    @tasks.loop(hours=24)
    async def generate_reports(self):
        try:
            config = await self.db.config.find_one({"_id": "bot_config"})
            if not config or not config.get("analytics_channel"):
                return
                
            channel = self.bot.get_channel(config["analytics_channel"])
            if not channel:
                return
            
            report = await self.generate_daily_report()
            await channel.send(embed=report)
            
        except Exception as e:
            self.bot.logger.error(f"Error generating reports: {e}")
    
    async def generate_daily_report(self) -> discord.Embed:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        new_users = await self.db.users.count_documents({
            "account_created": {"$gte": yesterday, "$lt": now}
        })
        
        daily_claims = await self.db.users.aggregate([
            {"$match": {"last_claim.date": {"$gte": yesterday, "$lt": now}}},
            {"$count": "total"}
        ]).to_list(1)
        
        cookie_stats = await self.db.statistics.find_one({"_id": "global_stats"})
        
        embed = discord.Embed(
            title="📊 Daily Analytics Report",
            color=0x5865f2,
            timestamp=now
        )
        
        embed.add_field(
            name="👥 User Activity",
            value=f"New Users: **{new_users}**\nDaily Claims: **{daily_claims[0]['total'] if daily_claims else 0}**",
            inline=True
        )
        
        if cookie_stats:
            top_cookies = sorted(
                cookie_stats.get("total_claims", {}).items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            if top_cookies:
                cookie_text = "\n".join([f"{i+1}. {c[0]}: {c[1]}" for i, c in enumerate(top_cookies)])
                embed.add_field(
                    name="🍪 Top Cookies",
                    value=cookie_text,
                    inline=True
                )
        
        embed.add_field(
            name="🏠 Server Stats",
            value=f"Total Servers: **{len(self.bot.guilds)}**\nTotal Members: **{sum(g.member_count for g in self.bot.guilds)}**",
            inline=True
        )
        
        return embed

    @commands.hybrid_command(name="analytics", description="View bot analytics dashboard")
    @commands.has_permissions(administrator=True)
    async def analytics(self, ctx):
        embed = discord.Embed(
            title="📊 Analytics Dashboard",
            description="Select an analytics category to view:",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        data_types = ["overview", "cookies", "users", "economy", "server", "trends"]
        view = AnalyticsView(data_types)
        
        message = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.selected_type:
            if view.selected_type == "overview":
                await self.show_overview(ctx, message)
            elif view.selected_type == "cookies":
                await self.show_cookie_analytics(ctx, message)
            elif view.selected_type == "users":
                await self.show_user_analytics(ctx, message)
            elif view.selected_type == "economy":
                await self.show_economy_analytics(ctx, message)
            elif view.selected_type == "server":
                await self.show_server_analytics(ctx, message)
            elif view.selected_type == "trends":
                await self.show_trends(ctx, message)
    
    async def show_overview(self, ctx, message):
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        
        total_users = await self.db.users.count_documents({})
        active_users = await self.db.users.count_documents({
            "last_active": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)}
        })
        
        total_points = await self.db.users.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$points"}}}
        ]).to_list(1)
        
        embed = discord.Embed(
            title="📊 Overview Analytics",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="👥 Users",
            value=f"Total: **{total_users:,}**\nActive (7d): **{active_users:,}**\nActivity Rate: **{(active_users/total_users*100):.1f}%**",
            inline=True
        )
        
        embed.add_field(
            name="💰 Economy",
            value=f"Total Points: **{total_points[0]['total']:,}**\nAvg Balance: **{(total_points[0]['total']/total_users):.0f}**" if total_points else "No data",
            inline=True
        )
        
        embed.add_field(
            name="🍪 Claims",
            value=f"All Time: **{stats.get('all_time_claims', 0):,}**\nThis Week: **{sum(stats.get('weekly_claims', {}).values()):,}**" if stats else "No data",
            inline=True
        )
        
        embed.add_field(
            name="🏠 Servers",
            value=f"Total: **{len(self.bot.guilds)}**\nMembers: **{sum(g.member_count for g in self.bot.guilds):,}**",
            inline=True
        )
        
        embed.add_field(
            name="⏰ Uptime",
            value=f"**{self.format_uptime()}**\nLatency: **{round(self.bot.latency * 1000)}ms**",
            inline=True
        )
        
        blacklisted = await self.db.users.count_documents({"blacklisted": True})
        premium = await self.db.users.count_documents({"premium_tier": {"$exists": True}})
        
        embed.add_field(
            name="📊 Other Stats",
            value=f"Blacklisted: **{blacklisted}**\nPremium Users: **{premium}**",
            inline=True
        )
        
        await message.edit(embed=embed, view=None)
    
    async def show_cookie_analytics(self, ctx, message):
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        if not stats:
            await message.edit(content="No cookie data available!", embed=None, view=None)
            return
        
        embed = discord.Embed(
            title="🍪 Cookie Analytics",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        total_claims = stats.get("total_claims", {})
        weekly_claims = stats.get("weekly_claims", {})
        
        if total_claims:
            sorted_cookies = sorted(total_claims.items(), key=lambda x: x[1], reverse=True)
            
            top_text = "\n".join([f"`{i+1}.` **{c[0]}**: {c[1]:,} claims" for i, c in enumerate(sorted_cookies[:10])])
            embed.add_field(name="🏆 Most Popular (All Time)", value=top_text or "No data", inline=False)
        
        if weekly_claims:
            sorted_weekly = sorted(weekly_claims.items(), key=lambda x: x[1], reverse=True)
            
            weekly_text = "\n".join([f"`{i+1}.` **{c[0]}**: {c[1]:,} claims" for i, c in enumerate(sorted_weekly[:5])])
            embed.add_field(name="📈 Trending This Week", value=weekly_text or "No data", inline=True)
        
        server = await self.db.servers.find_one({"server_id": ctx.guild.id})
        if server and server.get("cookies"):
            stock_info = []
            for cookie_type, config in server["cookies"].items():
                if os.path.exists(config.get("directory", "")):
                    files = len([f for f in os.listdir(config["directory"]) if f.endswith('.txt')])
                    stock_info.append(f"**{cookie_type}**: {files} files")
            
            if stock_info:
                embed.add_field(name="📦 Current Stock", value="\n".join(stock_info[:5]), inline=True)
        
        await message.edit(embed=embed, view=None)
    
    async def show_user_analytics(self, ctx, message):
        now = datetime.now(timezone.utc)
        
        total_users = await self.db.users.count_documents({})
        new_today = await self.db.users.count_documents({
            "account_created": {"$gte": now - timedelta(days=1)}
        })
        new_week = await self.db.users.count_documents({
            "account_created": {"$gte": now - timedelta(days=7)}
        })
        new_month = await self.db.users.count_documents({
            "account_created": {"$gte": now - timedelta(days=30)}
        })
        
        active_day = await self.db.users.count_documents({
            "last_active": {"$gte": now - timedelta(days=1)}
        })
        active_week = await self.db.users.count_documents({
            "last_active": {"$gte": now - timedelta(days=7)}
        })
        
        embed = discord.Embed(
            title="👥 User Analytics",
            color=0x5865f2,
            timestamp=now
        )
        
        embed.add_field(
            name="📊 User Growth",
            value=f"Total: **{total_users:,}**\nToday: **+{new_today}**\nThis Week: **+{new_week}**\nThis Month: **+{new_month}**",
            inline=True
        )
        
        embed.add_field(
            name="📈 Activity",
            value=f"Daily Active: **{active_day:,}** ({active_day/total_users*100:.1f}%)\nWeekly Active: **{active_week:,}** ({active_week/total_users*100:.1f}%)",
            inline=True
        )
        
        top_users = await self.db.users.find().sort("points", -1).limit(5).to_list(5)
        if top_users:
            rich_text = "\n".join([f"`{i+1}.` <@{u['user_id']}>: {u['points']:,} pts" for i, u in enumerate(top_users)])
            embed.add_field(name="💰 Richest Users", value=rich_text, inline=False)
        
        most_claims = await self.db.users.find().sort("total_claims", -1).limit(5).to_list(5)
        if most_claims:
            claim_text = "\n".join([f"`{i+1}.` <@{u['user_id']}>: {u['total_claims']:,} claims" for i, u in enumerate(most_claims)])
            embed.add_field(name="🍪 Most Active", value=claim_text, inline=True)
        
        high_trust = await self.db.users.find().sort("trust_score", -1).limit(5).to_list(5)
        if high_trust:
            trust_text = "\n".join([f"`{i+1}.` <@{u['user_id']}>: {u['trust_score']}/100" for i, u in enumerate(high_trust)])
            embed.add_field(name="⭐ Most Trusted", value=trust_text, inline=True)
        
        await message.edit(embed=embed, view=None)
    
    async def show_economy_analytics(self, ctx, message):
        total_points = await self.db.users.aggregate([
            {"$group": {"_id": None, "sum": {"$sum": "$points"}}}
        ]).to_list(1)
        
        total_earned = await self.db.users.aggregate([
            {"$group": {"_id": None, "sum": {"$sum": "$total_earned"}}}
        ]).to_list(1)
        
        total_spent = await self.db.users.aggregate([
            {"$group": {"_id": None, "sum": {"$sum": "$total_spent"}}}
        ]).to_list(1)
        
        wealth_distribution = await self.db.users.aggregate([
            {"$bucket": {
                "groupBy": "$points",
                "boundaries": [0, 100, 500, 1000, 5000, 10000, 50000, 100000],
                "default": "100000+",
                "output": {"count": {"$sum": 1}}
            }}
        ]).to_list(10)
        
        embed = discord.Embed(
            title="💰 Economy Analytics",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="💵 Circulation",
            value=f"Total: **{total_points[0]['sum']:,}** points\nEarned: **{total_earned[0]['sum']:,}**\nSpent: **{total_spent[0]['sum']:,}**" if total_points else "No data",
            inline=True
        )
        
        avg_balance = total_points[0]['sum'] / await self.db.users.count_documents({}) if total_points else 0
        embed.add_field(
            name="📊 Averages",
            value=f"Avg Balance: **{avg_balance:,.0f}**\nMedian: **~{avg_balance * 0.6:,.0f}**",
            inline=True
        )
        
        if wealth_distribution:
            dist_text = ""
            brackets = ["0-100", "100-500", "500-1k", "1k-5k", "5k-10k", "10k-50k", "50k-100k", "100k+"]
            for i, bucket in enumerate(wealth_distribution):
                if i < len(brackets):
                    dist_text += f"**{brackets[i]}**: {bucket.get('count', 0)} users\n"
            
            embed.add_field(name="📈 Wealth Distribution", value=dist_text[:1024], inline=False)
        
        lottery = await self.db.lottery.find_one({"_id": "current"})
        if lottery:
            embed.add_field(
                name="🎰 Lottery Pool",
                value=f"Current: **{lottery.get('pool', 0):,}** points\nParticipants: **{len(lottery.get('participants', []))}**",
                inline=True
            )
        
        await message.edit(embed=embed, view=None)
    
    async def show_server_analytics(self, ctx, message):
        server = await self.db.servers.find_one({"server_id": ctx.guild.id})
        if not server:
            await message.edit(content="No server data available!", embed=None, view=None)
            return
        
        embed = discord.Embed(
            title="🏠 Server Analytics",
            description=f"Analytics for **{ctx.guild.name}**",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        member_ids = [m.id for m in ctx.guild.members if not m.bot]
        server_users = await self.db.users.count_documents({"user_id": {"$in": member_ids}})
        
        embed.add_field(
            name="👥 Members",
            value=f"Total: **{ctx.guild.member_count}**\nRegistered: **{server_users}** ({server_users/len(member_ids)*100:.1f}%)",
            inline=True
        )
        
        server_claims = await self.db.users.aggregate([
            {"$match": {"user_id": {"$in": member_ids}}},
            {"$group": {"_id": None, "total": {"$sum": "$total_claims"}}}
        ]).to_list(1)
        
        embed.add_field(
            name="🍪 Claims",
            value=f"Total: **{server_claims[0]['total']:,}**" if server_claims else "No claims yet",
            inline=True
        )
        
        boosters = len([m for m in ctx.guild.members if ctx.guild.premium_subscriber_role in m.roles])
        embed.add_field(
            name="🚀 Boosters",
            value=f"**{boosters}** members\nLevel **{ctx.guild.premium_tier}**",
            inline=True
        )
        
        if server.get("cookies"):
            enabled_cookies = [c for c, cfg in server["cookies"].items() if cfg.get("enabled", True)]
            embed.add_field(
                name="🍪 Cookies",
                value=f"Types: **{len(enabled_cookies)}**\nEnabled: {', '.join(enabled_cookies[:5])}{'...' if len(enabled_cookies) > 5 else ''}",
                inline=False
            )
        
        if server.get("roles"):
            role_list = []
            for role_id, role_config in list(server["roles"].items())[:5]:
                role = ctx.guild.get_role(int(role_id))
                if role:
                    role_list.append(f"• {role.mention}: {len(role.members)} members")
            
            if role_list:
                embed.add_field(
                    name="🎭 Special Roles",
                    value="\n".join(role_list),
                    inline=False
                )
        
        await message.edit(embed=embed, view=None)
    
    async def show_trends(self, ctx, message):
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        analytics_data = await self.db.analytics.find({
            "timestamp": {"$gte": week_ago}
        }).sort("timestamp", 1).to_list(None)
        
        if not analytics_data:
            await message.edit(content="Not enough data for trends!", embed=None, view=None)
            return
        
        embed = discord.Embed(
            title="📈 7-Day Trends",
            color=0x5865f2,
            timestamp=now
        )
        
        if len(analytics_data) >= 2:
            start_users = analytics_data[0].get("users", {}).get("total", 0)
            end_users = analytics_data[-1].get("users", {}).get("total", 0)
            user_growth = ((end_users - start_users) / start_users * 100) if start_users > 0 else 0
            
            embed.add_field(
                name="👥 User Growth",
                value=f"Start: **{start_users:,}**\nEnd: **{end_users:,}**\nGrowth: **{user_growth:+.1f}%**",
                inline=True
            )
            
            start_points = analytics_data[0].get("economy", {}).get("total_points", 0)
            end_points = analytics_data[-1].get("economy", {}).get("total_points", 0)
            points_change = end_points - start_points
            
            embed.add_field(
                name="💰 Economy",
                value=f"Points Change: **{points_change:+,}**\nDaily Avg: **{points_change/7:+,.0f}**",
                inline=True
            )
        
        daily_active = []
        for data in analytics_data[-7:]:
            daily_active.append(data.get("users", {}).get("active_weekly", 0))
        
        if daily_active:
            avg_active = sum(daily_active) / len(daily_active)
            embed.add_field(
                name="📊 Activity Trend",
                value=f"Avg Active: **{avg_active:.0f}**\nPeak: **{max(daily_active)}**\nLow: **{min(daily_active)}**",
                inline=True
            )
        
        growth_rate = []
        for i in range(1, len(analytics_data)):
            prev = analytics_data[i-1].get("users", {}).get("total", 1)
            curr = analytics_data[i].get("users", {}).get("total", 1)
            rate = ((curr - prev) / prev * 100) if prev > 0 else 0
            growth_rate.append(rate)
        
        if growth_rate:
            embed.add_field(
                name="📈 Growth Rate",
                value=f"Average: **{sum(growth_rate)/len(growth_rate):.2f}%** daily\nBest Day: **{max(growth_rate):.2f}%**",
                inline=False
            )
        
        await message.edit(embed=embed, view=None)
    
    def format_uptime(self) -> str:
        uptime = datetime.now(timezone.utc) - self.bot.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) or "Just started"

    @commands.hybrid_command(name="export", description="Export analytics data")
    @commands.is_owner()
    async def export(self, ctx, data_type: str = "summary"):
        await ctx.defer()
        
        if data_type == "summary":
            data = await self.generate_summary_export()
        elif data_type == "users":
            data = await self.generate_users_export()
        elif data_type == "cookies":
            data = await self.generate_cookies_export()
        else:
            await ctx.send("❌ Invalid export type! Choose: summary, users, cookies", ephemeral=True)
            return
        
        json_data = json.dumps(data, indent=2, default=str)
        file = discord.File(
            io.StringIO(json_data),
            filename=f"analytics_{data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        embed = discord.Embed(
            title="📊 Analytics Export",
            description=f"Exported **{data_type}** data",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="📁 Format", value="JSON", inline=True)
        embed.add_field(name="📏 Size", value=f"{len(json_data):,} bytes", inline=True)
        
        await ctx.send(embed=embed, file=file, ephemeral=True)
    
    async def generate_summary_export(self) -> dict:
        return {
            "export_date": datetime.now(timezone.utc),
            "bot_info": {
                "name": str(self.bot.user),
                "servers": len(self.bot.guilds),
                "users": sum(g.member_count for g in self.bot.guilds)
            },
            "statistics": {
                "total_users": await self.db.users.count_documents({}),
                "total_claims": await self.db.users.aggregate([
                    {"$group": {"_id": None, "total": {"$sum": "$total_claims"}}}
                ]).to_list(1),
                "total_points": await self.db.users.aggregate([
                    {"$group": {"_id": None, "total": {"$sum": "$points"}}}
                ]).to_list(1)
            }
        }
    
    async def generate_users_export(self) -> dict:
        users = await self.db.users.find({}, {
            "user_id": 1, "points": 1, "total_claims": 1,
            "trust_score": 1, "level": 1, "account_created": 1
        }).to_list(None)
        
        return {
            "export_date": datetime.now(timezone.utc),
            "total_users": len(users),
            "users": users
        }
    
    async def generate_cookies_export(self) -> dict:
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        
        return {
            "export_date": datetime.now(timezone.utc),
            "cookie_statistics": stats.get("total_claims", {}) if stats else {},
            "weekly_claims": stats.get("weekly_claims", {}) if stats else {}
        }

async def setup(bot):
    await bot.add_cog(AnalyticsCog(bot))