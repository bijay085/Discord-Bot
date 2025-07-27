# cogs/economy.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import random
import asyncio
from typing import Optional

class ShopView(discord.ui.View):
    def __init__(self, items: list, user_points: int, page: int = 0):
        super().__init__(timeout=120)
        self.items = items
        self.user_points = user_points
        self.page = page
        self.max_page = (len(items) - 1) // 5
        
        self.update_buttons()
        
    def update_buttons(self):
        self.clear_items()
        
        if self.page > 0:
            self.add_item(discord.ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="prev"))
        
        start = self.page * 5
        end = min(start + 5, len(self.items))
        
        for i in range(start, end):
            item = self.items[i]
            affordable = self.user_points >= item["cost"]
            self.add_item(discord.ui.Button(
                label=f"{item['emoji']} {item['name']} ({item['cost']} pts)",
                style=discord.ButtonStyle.success if affordable else discord.ButtonStyle.danger,
                custom_id=f"buy_{i}",
                disabled=not affordable
            ))
        
        if self.page < self.max_page:
            self.add_item(discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="next"))

class TradeModal(discord.ui.Modal, title="💱 Trade Points"):
    def __init__(self):
        super().__init__()
        
        self.user = discord.ui.TextInput(
            label="Recipient Username or ID",
            placeholder="Enter username#0000 or user ID",
            required=True
        )
        self.add_item(self.user)
        
        self.amount = discord.ui.TextInput(
            label="Amount to Send",
            placeholder="Enter amount of points",
            required=True,
            max_length=10
        )
        self.add_item(self.amount)
        
        self.message = discord.ui.TextInput(
            label="Message (Optional)",
            style=discord.TextStyle.short,
            placeholder="Add a message...",
            required=False,
            max_length=100
        )
        self.add_item(self.message)

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.reset_weekly_stats.start()
        self.lottery_draw.start()
        
    def cog_unload(self):
        self.reset_weekly_stats.cancel()
        self.lottery_draw.cancel()
        
    @tasks.loop(hours=168)
    async def reset_weekly_stats(self):
        try:
            await self.db.users.update_many(
                {},
                {"$set": {"weekly_claims": 0}}
            )
            
            await self.db.statistics.update_one(
                {"_id": "global_stats"},
                {
                    "$set": {
                        "weekly_claims": {},
                        "week_start": datetime.now(timezone.utc)
                    }
                }
            )
        except Exception as e:
            self.bot.logger.error(f"Error resetting weekly stats: {e}")
    
    @tasks.loop(hours=24)
    async def lottery_draw(self):
        try:
            lottery = await self.db.lottery.find_one({"_id": "current"})
            if not lottery or datetime.now(timezone.utc) < lottery.get("draw_time"):
                return
            
            if not lottery.get("participants"):
                await self.db.lottery.delete_one({"_id": "current"})
                return
            
            winner_id = random.choice(lottery["participants"])
            prize = lottery["pool"]
            
            await self.db.users.update_one(
                {"user_id": winner_id},
                {"$inc": {"points": prize}}
            )
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            if config and config.get("main_log_channel"):
                channel = self.bot.get_channel(config["main_log_channel"])
                if channel:
                    embed = discord.Embed(
                        title="🎰 Lottery Winner!",
                        description=f"<@{winner_id}> won **{prize}** points!",
                        color=0xffd700,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="🎟️ Total Tickets", value=len(lottery["participants"]), inline=True)
                    embed.add_field(name="💰 Prize Pool", value=f"{prize} points", inline=True)
                    await channel.send(embed=embed)
            
            await self.db.lottery.delete_one({"_id": "current"})
            
            await self.db.lottery.insert_one({
                "_id": "current",
                "pool": 0,
                "participants": [],
                "draw_time": datetime.now(timezone.utc) + timedelta(days=7)
            })
            
        except Exception as e:
            self.bot.logger.error(f"Error in lottery draw: {e}")

    @commands.hybrid_command(name="balance", description="Check your or someone's balance")
    async def balance(self, ctx, user: Optional[discord.Member] = None):
        if user is None:
            user = ctx.author
            
        user_data = await self.db.users.find_one({"user_id": user.id})
        if not user_data:
            if user == ctx.author:
                user_data = {"points": 0, "level": 1, "xp": 0}
            else:
                embed = discord.Embed(
                    title="❌ User Not Found",
                    description="This user hasn't used the bot yet!",
                    color=0xff0000
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
        
        embed = discord.Embed(
            title=f"💰 {user.display_name}'s Balance",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(name="💵 Points", value=f"```{user_data.get('points', 0):,}```", inline=True)
        embed.add_field(name="🎯 Level", value=f"```Level {user_data.get('level', 1)}```", inline=True)
        embed.add_field(name="✨ XP", value=f"```{user_data.get('xp', 0):,}/{(user_data.get('level', 1) * 100):,}```", inline=True)
        
        rank = await self.get_user_rank(user.id)
        embed.add_field(name="🏆 Global Rank", value=f"```#{rank}```", inline=True)
        embed.add_field(name="⭐ Trust Score", value=f"```{user_data.get('trust_score', 50)}/100```", inline=True)
        embed.add_field(name="🎁 Total Earned", value=f"```{user_data.get('total_earned', 0):,}```", inline=True)
        
        if user_data.get("badges"):
            badges = " ".join(user_data["badges"][:10])
            embed.add_field(name="🏅 Badges", value=badges, inline=False)
        
        await ctx.send(embed=embed)
    
    async def get_user_rank(self, user_id: int) -> int:
        pipeline = [
            {"$match": {"points": {"$exists": True}}},
            {"$sort": {"points": -1}},
            {"$group": {"_id": None, "users": {"$push": "$user_id"}}},
            {"$project": {"rank": {"$indexOfArray": ["$users", user_id]}}}
        ]
        
        result = await self.db.users.aggregate(pipeline).to_list(1)
        if result and result[0]["rank"] != -1:
            return result[0]["rank"] + 1
        return 0

    @commands.hybrid_command(name="leaderboard", description="View the points leaderboard")
    async def leaderboard(self, ctx, scope: str = "global"):
        embed = discord.Embed(
            title=f"🏆 {scope.title()} Leaderboard",
            color=0xffd700,
            timestamp=datetime.now(timezone.utc)
        )
        
        if scope == "server":
            member_ids = [m.id for m in ctx.guild.members if not m.bot]
            pipeline = [
                {"$match": {"user_id": {"$in": member_ids}}},
                {"$sort": {"points": -1}},
                {"$limit": 10}
            ]
        else:
            pipeline = [
                {"$sort": {"points": -1}},
                {"$limit": 10}
            ]
        
        users = await self.db.users.aggregate(pipeline).to_list(10)
        
        if not users:
            embed.description = "No users found!"
            await ctx.send(embed=embed)
            return
        
        leaderboard_text = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for i, user_data in enumerate(users):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            user = self.bot.get_user(user_data["user_id"])
            name = user.name if user else "Unknown User"
            points = user_data.get("points", 0)
            leaderboard_text += f"{medal} **{name}** - {points:,} points\n"
        
        embed.description = leaderboard_text
        
        user_rank = await self.get_user_rank(ctx.author.id)
        if user_rank > 10:
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            points = user_data.get("points", 0) if user_data else 0
            embed.add_field(
                name="📍 Your Position",
                value=f"Rank **#{user_rank}** with **{points:,}** points",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="shop", description="View the points shop")
    async def shop(self, ctx):
        shop_items = [
            {"name": "Cookie Voucher", "cost": 50, "emoji": "🎟️", "description": "Get 1 free cookie claim"},
            {"name": "XP Booster", "cost": 100, "emoji": "⚡", "description": "2x XP for 24 hours"},
            {"name": "Lucky Charm", "cost": 150, "emoji": "🍀", "description": "Increased drop rates"},
            {"name": "Name Color", "cost": 200, "emoji": "🎨", "description": "Custom name color"},
            {"name": "Custom Badge", "cost": 300, "emoji": "🏅", "description": "Design your own badge"},
            {"name": "Premium Week", "cost": 500, "emoji": "💎", "description": "1 week premium access"},
            {"name": "Mystery Box", "cost": 250, "emoji": "📦", "description": "Random rewards"},
            {"name": "Cookie Bundle", "cost": 400, "emoji": "🍪", "description": "5 random cookies"},
            {"name": "VIP Pass", "cost": 1000, "emoji": "👑", "description": "1 month VIP status"},
            {"name": "Lottery Ticket", "cost": 25, "emoji": "🎰", "description": "Enter weekly lottery"}
        ]
        
        user_data = await self.db.users.find_one({"user_id": ctx.author.id})
        user_points = user_data.get("points", 0) if user_data else 0
        
        embed = discord.Embed(
            title="🛍️ Points Shop",
            description=f"Your balance: **{user_points:,}** points",
            color=0x5865F2
        )
        embed.set_footer(text="Click a button to purchase")
        
        view = ShopView(shop_items, user_points)
        
        async def update_embed(page):
            embed.clear_fields()
            start = page * 5
            end = min(start + 5, len(shop_items))
            
            for i in range(start, end):
                item = shop_items[i]
                embed.add_field(
                    name=f"{item['emoji']} {item['name']}",
                    value=f"{item['description']}\n💰 **{item['cost']}** points",
                    inline=False
                )
            
            embed.set_footer(text=f"Page {page + 1}/{view.max_page + 1} • Click a button to purchase")
        
        await update_embed(0)
        message = await ctx.send(embed=embed, view=view)
        
        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ This isn't your shop menu!", ephemeral=True)
                return
            
            custom_id = interaction.data["custom_id"]
            
            if custom_id == "prev":
                view.page -= 1
                view.update_buttons()
                await update_embed(view.page)
                await interaction.response.edit_message(embed=embed, view=view)
            elif custom_id == "next":
                view.page += 1
                view.update_buttons()
                await update_embed(view.page)
                await interaction.response.edit_message(embed=embed, view=view)
            elif custom_id.startswith("buy_"):
                item_index = int(custom_id.split("_")[1])
                item = shop_items[item_index]
                await self.process_purchase(interaction, ctx.author, item, user_points)
        
        for item in view.children:
            item.callback = button_callback

    async def process_purchase(self, interaction, user, item, current_points):
        if current_points < item["cost"]:
            await interaction.response.send_message("❌ Insufficient points!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {"$inc": {"points": -item["cost"]}}
        )
        
        embed = discord.Embed(
            title="✅ Purchase Successful!",
            description=f"You bought **{item['emoji']} {item['name']}** for **{item['cost']}** points!",
            color=0x00ff00
        )
        embed.add_field(name="💳 New Balance", value=f"{current_points - item['cost']:,} points", inline=True)
        
        if item["name"] == "Lottery Ticket":
            await self.db.lottery.update_one(
                {"_id": "current"},
                {
                    "$addToSet": {"participants": user.id},
                    "$inc": {"pool": 20}
                },
                upsert=True
            )
            embed.add_field(name="🎰 Lottery", value="You're entered in the weekly draw!", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(
                interaction.guild.id,
                f"🛍️ {user.mention} purchased **{item['name']}** for {item['cost']} points",
                discord.Color.blue()
            )

    @commands.hybrid_command(name="trade", description="Trade points with another user")
    async def trade(self, ctx):
        modal = TradeModal()
        await ctx.interaction.response.send_modal(modal)
        
        await modal.wait()
        
        try:
            amount = int(modal.amount.value)
            if amount <= 0:
                raise ValueError
        except:
            await ctx.followup.send("❌ Invalid amount!", ephemeral=True)
            return
        
        sender_data = await self.db.users.find_one({"user_id": ctx.author.id})
        if not sender_data or sender_data.get("points", 0) < amount:
            await ctx.followup.send("❌ Insufficient points!", ephemeral=True)
            return
        
        try:
            if modal.user.value.isdigit():
                recipient = self.bot.get_user(int(modal.user.value))
            else:
                recipient = discord.utils.get(self.bot.users, name=modal.user.value.split("#")[0])
            
            if not recipient or recipient.bot or recipient.id == ctx.author.id:
                raise ValueError
        except:
            await ctx.followup.send("❌ Invalid recipient!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": ctx.author.id},
            {"$inc": {"points": -amount}}
        )
        
        await self.db.users.update_one(
            {"user_id": recipient.id},
            {
                "$inc": {"points": amount},
                "$setOnInsert": {
                    "username": str(recipient),
                    "total_earned": 0,
                    "total_spent": 0,
                    "trust_score": 50,
                    "level": 1,
                    "xp": 0
                }
            },
            upsert=True
        )
        
        embed = discord.Embed(
            title="✅ Trade Successful!",
            description=f"Sent **{amount:,}** points to {recipient.mention}",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        if modal.message.value:
            embed.add_field(name="📝 Message", value=modal.message.value, inline=False)
        
        await ctx.followup.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="💰 Points Received!",
                description=f"{ctx.author.mention} sent you **{amount:,}** points!",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            if modal.message.value:
                dm_embed.add_field(name="📝 Message", value=modal.message.value, inline=False)
            await recipient.send(embed=dm_embed)
        except:
            pass

    @commands.hybrid_command(name="lottery", description="Check lottery status")
    async def lottery(self, ctx):
        lottery = await self.db.lottery.find_one({"_id": "current"})
        if not lottery:
            lottery = {
                "pool": 0,
                "participants": [],
                "draw_time": datetime.now(timezone.utc) + timedelta(days=7)
            }
            await self.db.lottery.insert_one(lottery)
        
        embed = discord.Embed(
            title="🎰 Weekly Lottery",
            color=0xffd700,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="💰 Prize Pool", value=f"```{lottery['pool']:,} points```", inline=True)
        embed.add_field(name="🎟️ Participants", value=f"```{len(lottery['participants'])}```", inline=True)
        embed.add_field(name="⏰ Next Draw", value=f"<t:{int(lottery['draw_time'].timestamp())}:R>", inline=True)
        
        is_entered = ctx.author.id in lottery.get("participants", [])
        embed.add_field(
            name="📍 Your Status",
            value="✅ Entered" if is_entered else "❌ Not Entered\nBuy a ticket in `/shop`",
            inline=False
        )
        
        if lottery['participants']:
            recent = lottery['participants'][-5:]
            recent_users = []
            for uid in recent:
                user = self.bot.get_user(uid)
                recent_users.append(user.name if user else f"User {uid}")
            embed.add_field(
                name="🎟️ Recent Entries",
                value="\n".join(f"• {u}" for u in recent_users),
                inline=False
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))