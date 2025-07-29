import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

class RobView(discord.ui.View):
    def __init__(self, robber, victim, success_chance):
        super().__init__(timeout=30)
        self.robber = robber
        self.victim = victim
        self.success_chance = success_chance
        self.result = None
        
    @discord.ui.button(label="🎯 Confirm Rob", style=discord.ButtonStyle.danger)
    async def confirm_rob(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.robber.id:
            await interaction.response.send_message("❌ This isn't your robbery!", ephemeral=True)
            return
            
        button.disabled = True
        self.result = "confirmed"
        await interaction.response.edit_message(view=self)
        self.stop()
        
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_rob(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.robber.id:
            await interaction.response.send_message("❌ This isn't your robbery!", ephemeral=True)
            return
            
        for item in self.children:
            item.disabled = True
        self.result = "cancelled"
        await interaction.response.edit_message(view=self)
        self.stop()

class RobCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.rob_cooldowns = {}
        self.cleanup_cooldowns.start()
        
    async def cog_load(self):
        print("🎮 RobCog loaded")
        
    async def cog_unload(self):
        self.cleanup_cooldowns.cancel()
        self.rob_cooldowns.clear()
        
    @tasks.loop(hours=1)
    async def cleanup_cooldowns(self):
        now = datetime.now(timezone.utc)
        to_remove = []
        
        for key, data in self.rob_cooldowns.items():
            if now - data["last_reset"] > timedelta(hours=24):
                to_remove.append(key)
                
        for key in to_remove:
            del self.rob_cooldowns[key]
            
    @cleanup_cooldowns.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
        
    async def get_user_data(self, user_id: int):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "username": str(user_id),
                "points": 0,
                "total_earned": 0,
                "total_spent": 0,
                "trust_score": 50,
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "daily_claimed": None,
                "invite_count": 0,
                "invited_users": [],
                "pending_invites": 0,
                "verified_invites": 0,
                "fake_invites": 0,
                "last_claim": None,
                "cookie_claims": {},
                "daily_claims": {},
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
                    "favorite_cookie": None,
                    "divine_gambles": 0,
                    "divine_wins": 0,
                    "divine_losses": 0,
                    "rob_wins": 0,
                    "rob_losses": 0,
                    "rob_winnings": 0,
                    "rob_losses_amount": 0,
                    "times_robbed": 0,
                    "amount_stolen_from": 0,
                    "slots_played": 0,
                    "slots_won": 0,
                    "slots_lost": 0,
                    "slots_profit": 0,
                    "slots_biggest_win": 0,
                    "slots_current_streak": 0,
                    "slots_best_streak": 0
                },
                "game_stats": {
                    "rob": {"attempts": 0, "successes": 0, "profit": 0}
                }
            }
        return user
        
    async def get_user_role_config(self, member: discord.Member, server: dict) -> dict:
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
                if role.position > highest_priority:
                    highest_priority = role.position
                    best_config = role_config
        
        return best_config
    
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    def calculate_success_chance(self, robber_trust: float, victim_trust: float, rob_bonus: int = 0) -> int:
        base_chance = 20
        
        if robber_trust == victim_trust:
            base_chance = 40
        elif robber_trust > victim_trust:
            if victim_trust < 20:
                base_chance = 90
            elif victim_trust < 40:
                base_chance = 70
            elif victim_trust < 60:
                base_chance = 50
            else:
                base_chance = 30
        
        return min(100, base_chance + rob_bonus)
    
    def calculate_points_to_steal(self, victim_points: float) -> float:
        if victim_points == 0:
            return 0
        elif victim_points < 3:
            return victim_points
        else:
            percentage = random.randint(20, 30) / 100
            return round(victim_points * percentage, 2)
    
    async def check_cooldowns(self, user_id: int, victim_id: int) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        
        rob_key = f"rob_{user_id}"
        if rob_key not in self.rob_cooldowns:
            self.rob_cooldowns[rob_key] = {
                "attempts": 0,
                "last_attempt": now - timedelta(hours=3),
                "last_reset": now,
                "targets": {}
            }
        
        robbed_key = f"robbed_{victim_id}"
        if robbed_key not in self.rob_cooldowns:
            self.rob_cooldowns[robbed_key] = {
                "times_robbed": 0,
                "last_robbed": now - timedelta(hours=3),
                "last_reset": now,
                "robbers": {}
            }
        
        rob_data = self.rob_cooldowns[rob_key]
        robbed_data = self.rob_cooldowns[robbed_key]
        
        if now - rob_data["last_reset"] > timedelta(hours=24):
            rob_data["attempts"] = 0
            rob_data["last_reset"] = now
            rob_data["targets"] = {}
        
        if now - robbed_data["last_reset"] > timedelta(hours=24):
            robbed_data["times_robbed"] = 0
            robbed_data["last_reset"] = now
            robbed_data["robbers"] = {}
        
        if rob_data["attempts"] >= 2:
            return False, "You've used all your rob attempts for today!"
        
        time_since_last = now - rob_data["last_attempt"]
        if time_since_last < timedelta(hours=3):
            remaining = timedelta(hours=3) - time_since_last
            minutes = int(remaining.total_seconds() / 60)
            return False, f"You must wait {minutes} minutes before robbing again!"
        
        if str(victim_id) in rob_data["targets"]:
            return False, "You can only rob the same person once per day!"
        
        if robbed_data["times_robbed"] >= 2:
            return False, "This person has been robbed too many times today!"
        
        time_since_robbed = now - robbed_data["last_robbed"]
        if time_since_robbed < timedelta(hours=3):
            remaining = timedelta(hours=3) - time_since_robbed
            minutes = int(remaining.total_seconds() / 60)
            return False, f"This person was robbed recently! Wait {minutes} minutes."
        
        return True, "OK"
    
    async def execute_rob(self, robber_id: int, victim_id: int, success_chance: int, robber_name: str = None, victim_name: str = None) -> dict:
        roll = random.randint(1, 100)
        success = roll <= success_chance
        
        robber_data = await self.get_user_data(robber_id)
        victim_data = await self.get_user_data(victim_id)
        
        robber_trust = robber_data.get("trust_score", 50)
        victim_trust = victim_data.get("trust_score", 50)
        
        result = {
            "success": success,
            "roll": roll,
            "chance": success_chance,
            "robber_points_before": robber_data["points"],
            "victim_points_before": victim_data["points"],
            "points_transferred": 0,
            "trust_change": 0
        }
        
        if victim_data["points"] == 0 and success:
            result["wasted"] = True
            result["success"] = False
            return result
        
        if success:
            points_to_steal = self.calculate_points_to_steal(victim_data["points"])
            result["points_transferred"] = points_to_steal
            result["trust_change"] = 0.5
            
            # Calculate new trust score
            new_robber_trust = min(100, robber_trust + 0.5)
            
            await self.db.users.update_one(
                {"user_id": robber_id},
                {
                    "$set": {
                        "trust_score": new_robber_trust
                    },
                    "$inc": {
                        "points": points_to_steal,
                        "game_stats.rob.successes": 1,
                        "game_stats.rob.profit": points_to_steal
                    }
                }
            )
            
            await self.db.users.update_one(
                {"user_id": victim_id},
                {
                    "$inc": {
                        "points": -points_to_steal,
                        "statistics.times_robbed": 1,
                        "statistics.amount_stolen_from": points_to_steal
                    }
                }
            )
            
            await self.db.rob_history.insert_one({
                "robber_id": robber_id,
                "victim_id": victim_id,
                "timestamp": datetime.now(timezone.utc),
                "success": True,
                "amount": points_to_steal,
                "robber_trust": robber_trust,
                "victim_trust": victim_trust
            })
        else:
            penalty = round(robber_data["points"] * 0.3, 2)
            result["points_transferred"] = penalty
            result["trust_change"] = -1
            
            # Calculate new trust score
            new_robber_trust = max(0, robber_trust - 1)
            
            await self.db.users.update_one(
                {"user_id": robber_id},
                {
                    "$set": {
                        "trust_score": new_robber_trust
                    },
                    "$inc": {
                        "points": -penalty,
                        "game_stats.rob.attempts": 1,
                        "game_stats.rob.profit": -penalty
                    }
                }
            )
            
            await self.db.users.update_one(
                {"user_id": victim_id},
                {
                    "$inc": {
                        "points": penalty
                    }
                }
            )
            
            await self.db.rob_history.insert_one({
                "robber_id": robber_id,
                "victim_id": victim_id,
                "timestamp": datetime.now(timezone.utc),
                "success": False,
                "penalty": penalty,
                "robber_trust": robber_trust,
                "victim_trust": victim_trust
            })
        
        await self.db.statistics.update_one(
            {"_id": "global_stats"},
            {
                "$inc": {
                    "game_stats.rob_attempts": 1,
                    "game_stats.rob_successes": 1 if success else 0
                }
            }
        )
        
        return result
    
    async def update_cooldowns(self, robber_id: int, victim_id: int):
        now = datetime.now(timezone.utc)
        
        rob_key = f"rob_{robber_id}"
        self.rob_cooldowns[rob_key]["attempts"] += 1
        self.rob_cooldowns[rob_key]["last_attempt"] = now
        self.rob_cooldowns[rob_key]["targets"][str(victim_id)] = now
        
        robbed_key = f"robbed_{victim_id}"
        self.rob_cooldowns[robbed_key]["times_robbed"] += 1
        self.rob_cooldowns[robbed_key]["last_robbed"] = now
        self.rob_cooldowns[robbed_key]["robbers"][str(robber_id)] = now
    
    @commands.hybrid_command(name="rob", description="Attempt to rob another user's points!")
    @app_commands.describe(target="The user you want to rob")
    async def rob(self, ctx, target: discord.Member):
        if target.id == ctx.author.id:
            await ctx.send("❌ You can't rob yourself!", ephemeral=True)
            return
            
        if target.bot:
            await ctx.send("❌ You can't rob bots!", ephemeral=True)
            return
        
        can_rob, reason = await self.check_cooldowns(ctx.author.id, target.id)
        if not can_rob:
            embed = discord.Embed(
                title="❌ Cannot Rob",
                description=reason,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        robber_data = await self.get_user_data(ctx.author.id)
        victim_data = await self.get_user_data(target.id)
        
        server = await self.db.servers.find_one({"server_id": ctx.guild.id})
        role_config = await self.get_user_role_config(ctx.author, server) if server else {}
        
        rob_bonus = role_config.get("game_benefits", {}).get("rob_success_bonus", 0) if role_config else 0
        
        success_chance = self.calculate_success_chance(
            robber_data.get("trust_score", 50),
            victim_data.get("trust_score", 50),
            rob_bonus
        )
        
        embed = discord.Embed(
            title="🎭 Rob Attempt",
            description=f"You're about to rob {target.mention}!",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Your Stats",
            value=f"Points: **{robber_data['points']}**\nTrust: **{robber_data.get('trust_score', 50)}**",
            inline=True
        )
        embed.add_field(
            name="🎯 Target Stats",
            value=f"Points: **???**\nTrust: **???**",
            inline=True
        )
        embed.add_field(
            name="🎲 Success Chance",
            value=f"**???**",
            inline=True
        )
        
        if rob_bonus > 0:
            embed.add_field(
                name="🎭 Role Bonus",
                value=f"+{rob_bonus}% success rate",
                inline=True
            )
        
        embed.add_field(
            name="⚠️ Risk/Reward",
            value=f"**Win:** Steal 20-30% points, +0.5 trust\n**Lose:** Pay 30% penalty, -1 trust",
            inline=False
        )
        
        view = RobView(ctx.author, target, success_chance)
        msg = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.result == "cancelled":
            embed = discord.Embed(
                title="❌ Rob Cancelled",
                description="You chickened out!",
                color=discord.Color.red()
            )
            await msg.edit(embed=embed, view=None)
            return
        
        if view.result != "confirmed":
            embed = discord.Embed(
                title="⏰ Too Slow!",
                description="You took too long to decide!",
                color=discord.Color.red()
            )
            await msg.edit(embed=embed, view=None)
            return
        
        loading_embed = discord.Embed(
            title="🎲 Rolling the dice...",
            description="Attempting robbery...",
            color=discord.Color.yellow()
        )
        await msg.edit(embed=loading_embed, view=None)
        
        await asyncio.sleep(2)
        
        result = await self.execute_rob(ctx.author.id, target.id, success_chance, str(ctx.author), str(target))
        
        if result.get("wasted"):
            embed = discord.Embed(
                title="💀 ROB ATTEMPT WASTED!",
                description=f"{target.mention} had **0 points**!",
                color=discord.Color.dark_red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Result", value="No points gained", inline=True)
            embed.add_field(name="Attempts Left", value=f"{2 - self.rob_cooldowns[f'rob_{ctx.author.id}']['attempts'] - 1}/2", inline=True)
            embed.set_footer(text="Choose your targets more wisely!")
            
            await self.update_cooldowns(ctx.author.id, target.id)
            await msg.edit(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"💀 {ctx.author.mention} wasted a rob attempt on {target.mention} (0 points)",
                discord.Color.dark_gray()
            )
            return
        
        if result["success"]:
            embed = discord.Embed(
                title="💰 ROBBERY SUCCESSFUL!",
                description=f"You successfully robbed {target.mention}!",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="💵 Stolen", value=f"**{result['points_transferred']}** points", inline=True)
            embed.add_field(name="📈 Trust Gained", value=f"**+{result['trust_change']}**", inline=True)
            embed.add_field(name="💰 Your Balance", value=f"**{result['robber_points_before'] + result['points_transferred']:.2f}**", inline=True)
            
            if rob_bonus > 0:
                embed.set_footer(text=f"Role bonus applied: +{rob_bonus}% success rate")
            
            await self.log_action(
                ctx.guild.id,
                f"💰 {ctx.author.mention} successfully robbed **{result['points_transferred']}** points from {target.mention}!",
                discord.Color.green()
            )
            
            try:
                robber_dm = discord.Embed(
                    title="💰 Robbery Successful - Detailed Report",
                    description=f"You successfully robbed {target.name}!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                robber_dm.add_field(
                    name="📊 Why You Won",
                    value=f"Your trust ({robber_data.get('trust_score', 50)}) vs Their trust ({victim_data.get('trust_score', 50)})\n"
                          f"This gave you a **{success_chance}%** chance\n"
                          f"You rolled **{result['roll']}** (needed ≤{success_chance})",
                    inline=False
                )
                robber_dm.add_field(name="💵 Amount Stolen", value=f"**{result['points_transferred']}** points", inline=True)
                robber_dm.add_field(name="📈 Trust Gained", value=f"**+0.5** (now {min(100, robber_data.get('trust_score', 50) + 0.5)})", inline=True)
                robber_dm.add_field(
                    name="💰 Balance Change",
                    value=f"Before: **{result['robber_points_before']}**\n"
                          f"After: **{result['robber_points_before'] + result['points_transferred']:.2f}**",
                    inline=False
                )
                robber_dm.set_footer(text="Build more trust score for better success rates!")
                await ctx.author.send(embed=robber_dm)
            except:
                pass
            
            try:
                victim_dm = discord.Embed(
                    title="💸 You've Been Robbed!",
                    description=f"{ctx.author.name} successfully robbed you!",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                victim_dm.add_field(name="💵 Amount Lost", value=f"**{result['points_transferred']}** points", inline=True)
                victim_dm.add_field(name="💰 Points Remaining", value=f"**{victim_data['points'] - result['points_transferred']:.2f}**", inline=True)
                victim_dm.add_field(
                    name="💡 Protection Tip",
                    value="Build your trust score through feedback to reduce rob success chances against you!",
                    inline=False
                )
                victim_dm.set_footer(text=f"Robbed in: {ctx.guild.name}")
                await target.send(embed=victim_dm)
            except:
                pass
        else:
            embed = discord.Embed(
                title="🚨 CAUGHT RED-HANDED!",
                description=f"You failed to rob {target.mention}!",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="💸 Penalty", value=f"**-{result['points_transferred']}** points", inline=True)
            embed.add_field(name="📉 Trust Lost", value=f"**{result['trust_change']}**", inline=True)
            embed.add_field(name="💰 Your Balance", value=f"**{max(0, result['robber_points_before'] - result['points_transferred']):.2f}**", inline=True)
            
            await self.log_action(
                ctx.guild.id,
                f"🚨 {ctx.author.mention} failed to rob {target.mention} and paid **{result['points_transferred']}** points penalty!",
                discord.Color.red()
            )
            
            try:
                robber_dm = discord.Embed(
                    title="🚨 Robbery Failed - Detailed Report",
                    description=f"You were caught trying to rob {target.name}!",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                robber_dm.add_field(
                    name="📊 Why You Failed",
                    value=f"Your trust ({robber_data.get('trust_score', 50)}) vs Their trust ({victim_data.get('trust_score', 50)})\n"
                          f"This gave you only **{success_chance}%** chance\n"
                          f"You rolled **{result['roll']}** (needed ≤{success_chance})",
                    inline=False
                )
                robber_dm.add_field(name="💸 Penalty Paid", value=f"**{result['points_transferred']}** points (30% of your balance)", inline=True)
                robber_dm.add_field(name="📉 Trust Lost", value=f"**-1** (now {max(0, robber_data.get('trust_score', 50) - 1)})", inline=True)
                robber_dm.add_field(
                    name="💰 Balance Change", 
                    value=f"Before: **{result['robber_points_before']}**\n"
                          f"After: **{max(0, result['robber_points_before'] - result['points_transferred']):.2f}**",
                    inline=False
                )
                robber_dm.set_footer(text="Build more trust score for better success rates!")
                await ctx.author.send(embed=robber_dm)
            except:
                pass
            
            try:
                victim_dm = discord.Embed(
                    title="🛡️ Robbery Attempt Failed!",
                    description=f"{ctx.author.name} tried to rob you but failed!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                victim_dm.add_field(name="💵 Compensation", value=f"**+{result['points_transferred']}** points", inline=True)
                victim_dm.add_field(name="💰 New Balance", value=f"**{victim_data['points'] + result['points_transferred']:.2f}**", inline=True)
                victim_dm.add_field(
                    name="🎯 Defense Stats",
                    value=f"Your trust score ({victim_data.get('trust_score', 50)}) helped defend against the robbery!",
                    inline=False
                )
                victim_dm.set_footer(text=f"Defended in: {ctx.guild.name}")
                await target.send(embed=victim_dm)
            except:
                pass
        
        await self.update_cooldowns(ctx.author.id, target.id)
        await msg.edit(embed=embed)
    
    @commands.hybrid_command(name="robstats", description="Check your rob statistics")
    async def robstats(self, ctx):
        rob_key = f"rob_{ctx.author.id}"
        robbed_key = f"robbed_{ctx.author.id}"
        
        rob_data = self.rob_cooldowns.get(rob_key, {
            "attempts": 0,
            "last_attempt": datetime.now(timezone.utc) - timedelta(hours=3),
            "targets": {}
        })
        
        robbed_data = self.rob_cooldowns.get(robbed_key, {
            "times_robbed": 0,
            "last_robbed": datetime.now(timezone.utc) - timedelta(hours=3),
            "robbers": {}
        })
        
        user_data = await self.get_user_data(ctx.author.id)
        stats = user_data.get("game_stats", {}).get("rob", {})
        
        embed = discord.Embed(
            title="🎭 Your Rob Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        attempts_left = max(0, 2 - rob_data["attempts"])
        can_be_robbed = max(0, 2 - robbed_data["times_robbed"])
        
        embed.add_field(
            name="🎯 Rob Attempts",
            value=f"**{attempts_left}/2** remaining today",
            inline=True
        )
        embed.add_field(
            name="🛡️ Rob Protection",
            value=f"Can be robbed **{can_be_robbed}/2** more times",
            inline=True
        )
        
        if rob_data["last_attempt"]:
            next_rob = rob_data["last_attempt"] + timedelta(hours=3)
            if datetime.now(timezone.utc) < next_rob:
                minutes = int((next_rob - datetime.now(timezone.utc)).total_seconds() / 60)
                embed.add_field(
                    name="⏰ Next Rob",
                    value=f"Available in **{minutes}** minutes",
                    inline=False
                )
        
        embed.add_field(
            name="📊 Lifetime Stats",
            value=f"Successes: **{stats.get('successes', 0)}**\n"
                  f"Total Attempts: **{stats.get('attempts', 0) + stats.get('successes', 0)}**\n"
                  f"Net Profit: **{stats.get('profit', 0):.0f}** points",
            inline=False
        )
        
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed, ephemeral=True)
    
    @commands.hybrid_command(name="robhelp", description="Learn about the rob system")
    async def robhelp(self, ctx):
        embed = discord.Embed(
            title="🎭 Rob System Guide",
            description="Steal points from other users based on trust scores!",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="📊 Success Rates",
            value=(
                "Your chance depends on trust score difference:\n"
                "• Victim <20 trust: **90%** success\n"
                "• Victim 20-40: **70%** success\n"
                "• Victim 40-60: **50%** success\n"
                "• Victim 60+: **30%** success\n"
                "• Robbing higher trust: **20%** success"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💰 Rewards & Penalties",
            value=(
                "**Success:** Steal 20-30% points, +0.5 trust\n"
                "**Failure:** Pay 30% penalty, -1 trust\n"
                "**0 Points:** Waste attempt, no rewards"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⏰ Cooldowns",
            value=(
                "• Max 2 rob attempts per 24hr\n"
                "• 3hr cooldown between attempts\n"
                "• Can be robbed max 2 times per 24hr\n"
                "• Same target once per 24hr only"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎭 Role Benefits",
            value=(
                "Some roles provide rob success bonuses:\n"
                "• Check your role benefits with `/refresh`\n"
                "• Higher tier roles = better success rates"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Pro Tips",
            value=(
                "• Check target's trust score first\n"
                "• Higher trust = better rob success\n"
                "• Don't rob 0 point users\n"
                "• Build trust through feedback!"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RobCog(bot))