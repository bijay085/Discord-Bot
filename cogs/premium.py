# cogs/premium.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
from typing import Optional

class PremiumView(discord.ui.View):
    def __init__(self, tiers: dict):
        super().__init__(timeout=180)
        self.tiers = tiers
        self.selected_tier = None
        
        for tier_name, tier_data in tiers.items():
            button = discord.ui.Button(
                label=f"{tier_data['emoji']} {tier_name}",
                style=discord.ButtonStyle.primary if tier_name != "Ultimate" else discord.ButtonStyle.danger,
                custom_id=tier_name
            )
            self.add_item(button)

class BoostRewardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        
    @discord.ui.button(label="🎁 Claim Rewards", style=discord.ButtonStyle.success)
    async def claim_rewards(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)

class PremiumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_premium_expiry.start()
        self.boost_rewards.start()
        
        self.premium_tiers = {
            "Bronze": {
                "emoji": "🥉",
                "cost": 500,
                "duration": 7,
                "benefits": {
                    "daily_bonus": 2,
                    "cooldown_reduction": 0.25,
                    "cost_reduction": 0.1,
                    "xp_multiplier": 1.5,
                    "extra_claims": 1
                },
                "color": 0xcd7f32
            },
            "Silver": {
                "emoji": "🥈",
                "cost": 1500,
                "duration": 30,
                "benefits": {
                    "daily_bonus": 5,
                    "cooldown_reduction": 0.5,
                    "cost_reduction": 0.25,
                    "xp_multiplier": 2,
                    "extra_claims": 3
                },
                "color": 0xc0c0c0
            },
            "Gold": {
                "emoji": "🥇",
                "cost": 3000,
                "duration": 30,
                "benefits": {
                    "daily_bonus": 10,
                    "cooldown_reduction": 0.75,
                    "cost_reduction": 0.5,
                    "xp_multiplier": 3,
                    "extra_claims": 5
                },
                "color": 0xffd700
            },
            "Ultimate": {
                "emoji": "💎",
                "cost": 10000,
                "duration": 90,
                "benefits": {
                    "daily_bonus": 20,
                    "cooldown_reduction": 1,
                    "cost_reduction": 1,
                    "xp_multiplier": 5,
                    "extra_claims": 10
                },
                "color": 0x5865f2
            }
        }
        
    def cog_unload(self):
        self.check_premium_expiry.cancel()
        self.boost_rewards.cancel()
        
    @tasks.loop(hours=1)
    async def check_premium_expiry(self):
        try:
            now = datetime.now(timezone.utc)
            expired_users = await self.db.users.find({
                "premium_until": {"$lte": now},
                "premium_tier": {"$exists": True}
            }).to_list(None)
            
            for user_data in expired_users:
                await self.db.users.update_one(
                    {"user_id": user_data["user_id"]},
                    {
                        "$unset": {"premium_tier": "", "premium_until": ""},
                        "$push": {"notifications": {
                            "type": "premium_expired",
                            "message": "Your premium subscription has expired!",
                            "timestamp": now
                        }}
                    }
                )
                
                try:
                    user = self.bot.get_user(user_data["user_id"])
                    if user:
                        embed = discord.Embed(
                            title="⏰ Premium Expired",
                            description="Your premium subscription has expired!",
                            color=0xff0000,
                            timestamp=now
                        )
                        embed.add_field(
                            name="🔄 Renew Premium",
                            value="Use `/premium` to renew your subscription!",
                            inline=False
                        )
                        await user.send(embed=embed)
                except:
                    pass
                    
        except Exception as e:
            self.bot.logger.error(f"Error checking premium expiry: {e}")
    
    @tasks.loop(hours=24)
    async def boost_rewards(self):
        try:
            for guild in self.bot.guilds:
                boost_role = guild.premium_subscriber_role
                if not boost_role:
                    continue
                    
                for member in boost_role.members:
                    user_data = await self.db.users.find_one({"user_id": member.id})
                    if not user_data:
                        continue
                        
                    last_boost_reward = user_data.get("last_boost_reward")
                    if last_boost_reward:
                        if datetime.now(timezone.utc) - last_boost_reward < timedelta(days=1):
                            continue
                    
                    await self.db.users.update_one(
                        {"user_id": member.id},
                        {
                            "$inc": {"points": 50},
                            "$set": {"last_boost_reward": datetime.now(timezone.utc)},
                            "$push": {"notifications": {
                                "type": "boost_reward",
                                "message": "Daily boost reward: +50 points!",
                                "timestamp": datetime.now(timezone.utc)
                            }}
                        }
                    )
                    
        except Exception as e:
            self.bot.logger.error(f"Error in boost rewards: {e}")

    @commands.hybrid_command(name="premium", description="View and purchase premium subscriptions")
    async def premium(self, ctx):
        user_data = await self.db.users.find_one({"user_id": ctx.author.id})
        if not user_data:
            user_data = {"points": 0}
            
        embed = discord.Embed(
            title="✨ Premium Subscriptions",
            description="Unlock exclusive benefits with premium!",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        current_tier = user_data.get("premium_tier")
        if current_tier:
            premium_until = user_data.get("premium_until")
            embed.add_field(
                name="📍 Current Status",
                value=f"{self.premium_tiers[current_tier]['emoji']} **{current_tier}** until <t:{int(premium_until.timestamp())}:R>",
                inline=False
            )
        else:
            embed.add_field(
                name="📍 Current Status",
                value="❌ No active premium",
                inline=False
            )
        
        embed.add_field(
            name="💰 Your Balance",
            value=f"```{user_data.get('points', 0):,} points```",
            inline=False
        )
        
        for tier_name, tier_data in self.premium_tiers.items():
            benefits_text = (
                f"• +{tier_data['benefits']['daily_bonus']} daily points\n"
                f"• {int(tier_data['benefits']['cooldown_reduction']*100)}% faster cooldowns\n"
                f"• {int(tier_data['benefits']['cost_reduction']*100)}% cheaper cookies\n"
                f"• {tier_data['benefits']['xp_multiplier']}x XP gain\n"
                f"• +{tier_data['benefits']['extra_claims']} daily claims"
            )
            
            embed.add_field(
                name=f"{tier_data['emoji']} {tier_name} ({tier_data['duration']} days)",
                value=f"{benefits_text}\n💵 **{tier_data['cost']:,}** points",
                inline=True
            )
        
        view = PremiumView(self.premium_tiers)
        message = await ctx.send(embed=embed, view=view)
        
        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ This isn't your premium menu!", ephemeral=True)
                return
            
            tier_name = interaction.data["custom_id"]
            tier_data = self.premium_tiers[tier_name]
            
            if user_data.get("points", 0) < tier_data["cost"]:
                await interaction.response.send_message(
                    f"❌ You need **{tier_data['cost'] - user_data.get('points', 0):,}** more points!",
                    ephemeral=True
                )
                return
            
            confirm_embed = discord.Embed(
                title=f"{tier_data['emoji']} Confirm Purchase",
                description=f"Purchase **{tier_name}** premium for **{tier_data['cost']:,}** points?",
                color=tier_data["color"]
            )
            confirm_embed.add_field(
                name="📅 Duration",
                value=f"{tier_data['duration']} days",
                inline=True
            )
            confirm_embed.add_field(
                name="💳 New Balance",
                value=f"{user_data.get('points', 0) - tier_data['cost']:,} points",
                inline=True
            )
            
            confirm_view = discord.ui.View()
            confirm_button = discord.ui.Button(label="✅ Confirm", style=discord.ButtonStyle.success)
            cancel_button = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger)
            
            async def confirm_callback(confirm_interaction: discord.Interaction):
                await self.process_premium_purchase(confirm_interaction, ctx.author, tier_name, tier_data)
                
            async def cancel_callback(cancel_interaction: discord.Interaction):
                await cancel_interaction.response.edit_message(
                    content="❌ Purchase cancelled!",
                    embed=None,
                    view=None
                )
            
            confirm_button.callback = confirm_callback
            cancel_button.callback = cancel_callback
            
            confirm_view.add_item(confirm_button)
            confirm_view.add_item(cancel_button)
            
            await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
        
        for item in view.children:
            item.callback = button_callback
    
    async def process_premium_purchase(self, interaction, user, tier_name, tier_data):
        premium_until = datetime.now(timezone.utc) + timedelta(days=tier_data["duration"])
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$inc": {"points": -tier_data["cost"]},
                "$set": {
                    "premium_tier": tier_name,
                    "premium_until": premium_until,
                    "premium_benefits": tier_data["benefits"]
                }
            }
        )
        
        success_embed = discord.Embed(
            title=f"{tier_data['emoji']} Premium Activated!",
            description=f"You now have **{tier_name}** premium!",
            color=tier_data["color"],
            timestamp=datetime.now(timezone.utc)
        )
        success_embed.add_field(
            name="📅 Valid Until",
            value=f"<t:{int(premium_until.timestamp())}:F>",
            inline=False
        )
        success_embed.add_field(
            name="✨ Benefits Active",
            value="All premium benefits are now active!",
            inline=False
        )
        
        await interaction.response.edit_message(embed=success_embed, view=None)
        
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(
                interaction.guild.id,
                f"✨ {user.mention} purchased **{tier_name}** premium for {tier_data['cost']} points",
                discord.Color.from_rgb(*[int(tier_data["color"] >> i & 0xff) for i in (16, 8, 0)])
            )

    @commands.hybrid_command(name="boost", description="Claim server boost rewards")
    async def boost(self, ctx):
        if not ctx.guild.premium_subscriber_role in ctx.author.roles:
            embed = discord.Embed(
                title="❌ Not a Booster",
                description="You need to boost this server to use this command!",
                color=0xff0000
            )
            embed.add_field(
                name="🚀 Boost Benefits",
                value=(
                    "• Free cookies (0 cost)\n"
                    "• No cooldowns\n"
                    "• 50 daily points\n"
                    "• Exclusive badge\n"
                    "• Priority support"
                ),
                inline=False
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        user_data = await self.db.users.find_one({"user_id": ctx.author.id})
        if not user_data:
            user_data = {
                "points": 0,
                "boost_streak": 0,
                "last_boost_claim": None
            }
        
        last_claim = user_data.get("last_boost_claim")
        if last_claim:
            time_since = datetime.now(timezone.utc) - last_claim
            if time_since < timedelta(hours=24):
                next_claim = last_claim + timedelta(hours=24)
                embed = discord.Embed(
                    title="⏰ Already Claimed",
                    description=f"Next boost reward: <t:{int(next_claim.timestamp())}:R>",
                    color=0xffa500
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
        
        streak = user_data.get("boost_streak", 0)
        if last_claim and datetime.now(timezone.utc) - last_claim < timedelta(hours=48):
            streak += 1
        else:
            streak = 1
        
        base_reward = 50
        streak_bonus = min(streak * 5, 50)
        total_reward = base_reward + streak_bonus
        
        await self.db.users.update_one(
            {"user_id": ctx.author.id},
            {
                "$inc": {"points": total_reward},
                "$set": {
                    "last_boost_claim": datetime.now(timezone.utc),
                    "boost_streak": streak
                },
                "$addToSet": {"badges": "🚀"}
            },
            upsert=True
        )
        
        embed = discord.Embed(
            title="🚀 Boost Rewards Claimed!",
            color=0xff73fa,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        embed.add_field(name="💰 Base Reward", value=f"`{base_reward}` points", inline=True)
        embed.add_field(name="🔥 Streak Bonus", value=f"`{streak_bonus}` points", inline=True)
        embed.add_field(name="✨ Total", value=f"`{total_reward}` points", inline=True)
        
        embed.add_field(name="🎯 Current Streak", value=f"`{streak}` days", inline=True)
        embed.add_field(name="💎 Next Bonus", value=f"`+{min((streak + 1) * 5, 50)}` points", inline=True)
        embed.add_field(name="⏰ Next Claim", value="In 24 hours", inline=True)
        
        if streak >= 7:
            embed.add_field(
                name="🏆 Streak Achievement!",
                value=f"Amazing! You've maintained a **{streak}-day** streak!",
                inline=False
            )
        
        view = BoostRewardView()
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="benefits", description="View your active benefits")
    async def benefits(self, ctx, user: Optional[discord.Member] = None):
        if user is None:
            user = ctx.author
            
        user_data = await self.db.users.find_one({"user_id": user.id})
        if not user_data:
            embed = discord.Embed(
                title="❌ No Benefits",
                description=f"{user.mention} has no active benefits!",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"✨ {user.display_name}'s Benefits",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        active_benefits = []
        
        if user_data.get("premium_tier"):
            tier = user_data["premium_tier"]
            tier_data = self.premium_tiers[tier]
            benefits = user_data.get("premium_benefits", {})
            
            premium_text = (
                f"{tier_data['emoji']} **{tier} Premium**\n"
                f"• +{benefits.get('daily_bonus', 0)} daily points\n"
                f"• {int(benefits.get('cooldown_reduction', 0)*100)}% faster cooldowns\n"
                f"• {int(benefits.get('cost_reduction', 0)*100)}% cheaper cookies\n"
                f"• {benefits.get('xp_multiplier', 1)}x XP multiplier\n"
                f"• Expires: <t:{int(user_data['premium_until'].timestamp())}:R>"
            )
            active_benefits.append(("Premium Subscription", premium_text))
        
        if ctx.guild and ctx.guild.premium_subscriber_role in user.roles:
            boost_text = (
                "🚀 **Server Booster**\n"
                "• FREE cookies (100% discount)\n"
                "• NO cooldowns\n"
                "• 50 daily points\n"
                "• Exclusive badge\n"
                "• Priority support"
            )
            active_benefits.append(("Server Boost", boost_text))
        
        special_roles = []
        if ctx.guild:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if server and server.get("roles"):
                for role in user.roles:
                    role_config = server["roles"].get(str(role.id))
                    if role_config:
                        special_roles.append(f"• {role.name}: {role_config['cooldown']}h CD, {role_config['cost']} cost")
        
        if special_roles:
            active_benefits.append(("Special Roles", "\n".join(special_roles)))
        
        if user_data.get("badges"):
            badges_text = " ".join(user_data["badges"][:20])
            active_benefits.append(("Badges", badges_text))
        
        if active_benefits:
            for title, content in active_benefits:
                embed.add_field(name=title, value=content, inline=False)
        else:
            embed.description = "No active benefits!"
        
        total_discount = 0
        total_cooldown = 0
        
        if user_data.get("premium_benefits"):
            total_discount += user_data["premium_benefits"].get("cost_reduction", 0) * 100
            total_cooldown += user_data["premium_benefits"].get("cooldown_reduction", 0) * 100
        
        if ctx.guild and ctx.guild.premium_subscriber_role in user.roles:
            total_discount = 100
            total_cooldown = 100
        
        summary = f"💰 Total Discount: **{int(total_discount)}%**\n⏰ Cooldown Reduction: **{int(total_cooldown)}%**"
        embed.add_field(name="📊 Summary", value=summary, inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="gift", description="Gift premium to another user")
    async def gift(self, ctx, recipient: discord.Member, tier: str):
        if recipient.bot:
            await ctx.send("❌ You can't gift premium to bots!", ephemeral=True)
            return
            
        if recipient.id == ctx.author.id:
            await ctx.send("❌ You can't gift premium to yourself!", ephemeral=True)
            return
        
        tier = tier.title()
        if tier not in self.premium_tiers:
            valid_tiers = ", ".join(self.premium_tiers.keys())
            await ctx.send(f"❌ Invalid tier! Choose from: {valid_tiers}", ephemeral=True)
            return
        
        tier_data = self.premium_tiers[tier]
        user_data = await self.db.users.find_one({"user_id": ctx.author.id})
        
        if not user_data or user_data.get("points", 0) < tier_data["cost"]:
            await ctx.send("❌ Insufficient points!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎁 Gift Premium",
            description=f"Gift **{tier}** premium to {recipient.mention}?",
            color=tier_data["color"]
        )
        embed.add_field(name="💰 Cost", value=f"{tier_data['cost']:,} points", inline=True)
        embed.add_field(name="📅 Duration", value=f"{tier_data['duration']} days", inline=True)
        
        confirm_view = discord.ui.View()
        confirm = discord.ui.Button(label="✅ Confirm Gift", style=discord.ButtonStyle.success)
        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        
        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ This isn't your gift!", ephemeral=True)
                return
            
            premium_until = datetime.now(timezone.utc) + timedelta(days=tier_data["duration"])
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {"$inc": {"points": -tier_data["cost"]}}
            )
            
            await self.db.users.update_one(
                {"user_id": recipient.id},
                {
                    "$set": {
                        "premium_tier": tier,
                        "premium_until": premium_until,
                        "premium_benefits": tier_data["benefits"],
                        "premium_gifted_by": ctx.author.id
                    }
                },
                upsert=True
            )
            
            success_embed = discord.Embed(
                title="🎁 Gift Sent!",
                description=f"You gifted **{tier}** premium to {recipient.mention}!",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            await interaction.response.edit_message(embed=success_embed, view=None)
            
            try:
                gift_embed = discord.Embed(
                    title="🎁 You Received a Gift!",
                    description=f"{ctx.author.mention} gifted you **{tier}** premium!",
                    color=tier_data["color"],
                    timestamp=datetime.now(timezone.utc)
                )
                gift_embed.add_field(
                    name="✨ Benefits",
                    value=(
                        f"• +{tier_data['benefits']['daily_bonus']} daily points\n"
                        f"• {int(tier_data['benefits']['cooldown_reduction']*100)}% faster cooldowns\n"
                        f"• {int(tier_data['benefits']['cost_reduction']*100)}% cheaper cookies\n"
                        f"• {tier_data['benefits']['xp_multiplier']}x XP gain"
                    ),
                    inline=False
                )
                gift_embed.add_field(
                    name="📅 Valid Until",
                    value=f"<t:{int(premium_until.timestamp())}:F>",
                    inline=False
                )
                await recipient.send(embed=gift_embed)
            except:
                pass
            
            cookie_cog = self.bot.get_cog("CookieCog")
            if cookie_cog:
                await cookie_cog.log_action(
                    ctx.guild.id,
                    f"🎁 {ctx.author.mention} gifted **{tier}** premium to {recipient.mention}",
                    discord.Color.from_rgb(*[int(tier_data["color"] >> i & 0xff) for i in (16, 8, 0)])
                )
        
        async def cancel_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ This isn't your gift!", ephemeral=True)
                return
            await interaction.response.edit_message(content="❌ Gift cancelled!", embed=None, view=None)
        
        confirm.callback = confirm_callback
        cancel.callback = cancel_callback
        
        confirm_view.add_item(confirm)
        confirm_view.add_item(cancel)
        
        await ctx.send(embed=embed, view=confirm_view)

async def setup(bot):
    await bot.add_cog(PremiumCog(bot))