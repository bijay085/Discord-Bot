import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

class BetAmountModal(discord.ui.Modal):
    def __init__(self, gamble_cog, user_id: int):
        super().__init__(title="Enter Gamble Amount")
        self.gamble_cog = gamble_cog
        self.user_id = user_id
        
        self.amount = discord.ui.TextInput(
            label="How much trust do you want to gamble?",
            placeholder="Enter amount (min 15)...",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.amount)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            if amount < 15:
                await interaction.response.send_message("❌ Minimum gamble is 15 trust!", ephemeral=True)
                return
                
            await self.gamble_cog.process_divine_gamble(interaction, amount)
                
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount!", ephemeral=True)

class GambleView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.choice = None
        
    @discord.ui.button(label="🎲 Take the Gamble", style=discord.ButtonStyle.danger)
    async def confirm_gamble(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your gamble!", ephemeral=True)
            return
            
        self.choice = "confirmed"
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()
        
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_gamble(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your gamble!", ephemeral=True)
            return
            
        self.choice = "cancelled"
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

class GambleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.cleanup_roles.start()
        
    async def cog_load(self):
        print("🎮 GambleCog loaded")
        
    async def cog_unload(self):
        self.cleanup_roles.cancel()
        
    @tasks.loop(hours=1)
    async def cleanup_roles(self):
        try:
            async for gamble_data in self.db.divine_gambles.find({"status": "blessed", "role_expires": {"$lt": datetime.now(timezone.utc)}}):
                guild = self.bot.get_guild(gamble_data["guild_id"])
                if guild:
                    member = guild.get_member(gamble_data["user_id"])
                    divine_role = discord.utils.get(guild.roles, name="Divine Chosen")
                    if member and divine_role and divine_role in member.roles:
                        await member.remove_roles(divine_role)
                        
                await self.db.divine_gambles.update_one(
                    {"_id": gamble_data["_id"]},
                    {"$set": {"role_removed": True}}
                )
        except Exception as e:
            print(f"Error in cleanup_roles: {e}")
            
    @cleanup_roles.before_loop
    async def before_cleanup_roles(self):
        await self.bot.wait_until_ready()
        
    async def get_user_data(self, user_id: int):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "points": 0,
                "trust_score": 50,
                "game_stats": {
                    "gamble": {"attempts": 0, "wins": 0}
                }
            }
        return user
        
    async def get_user_role_config(self, member: discord.Member, server: dict) -> dict:
        if not server.get("role_based"):
            return {}
            
        best_config = {}
        highest_priority = -1
        
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
            
    async def count_active_invites(self, user_id: int) -> int:
        user_data = await self.db.users.find_one({"user_id": user_id})
        if not user_data:
            return 0
            
        active_count = 0
        for invited_user in user_data.get("invited_users", []):
            if invited_user.get("verified", False):
                active_count += 1
                
        return active_count
        
    async def check_cooldown(self, user_id: int) -> tuple[bool, Optional[datetime]]:
        last_gamble = await self.db.divine_gambles.find_one(
            {"user_id": user_id},
            sort=[("timestamp", -1)]
        )
        
        if not last_gamble:
            return True, None
            
        cooldown_end = last_gamble["timestamp"] + timedelta(days=7)
        if datetime.now(timezone.utc) < cooldown_end:
            return False, cooldown_end
            
        return True, None
        
    async def remove_divine_role_from_current(self, guild: discord.Guild):
        divine_role = discord.utils.get(guild.roles, name="Divine Chosen")
        if divine_role:
            for member in divine_role.members:
                await member.remove_roles(divine_role)
                await self.db.divine_gambles.update_many(
                    {"guild_id": guild.id, "user_id": member.id, "status": "blessed"},
                    {"$set": {"role_removed": True}}
                )
                
    async def create_or_get_roles(self, guild: discord.Guild):
        divine_role = None
        cursed_role = None
        
        server_data = await self.db.servers.find_one({"server_id": guild.id})
        
        if server_data and server_data.get("gamble_roles"):
            divine_role_id = server_data["gamble_roles"].get("divine_chosen_id")
            cursed_role_id = server_data["gamble_roles"].get("cursed_gambler_id")
            
            if divine_role_id:
                divine_role = guild.get_role(divine_role_id)
            if cursed_role_id:
                cursed_role = guild.get_role(cursed_role_id)
        
        if not divine_role:
            divine_role = discord.utils.get(guild.roles, name="Divine Chosen")
        
        if not cursed_role:
            cursed_role = discord.utils.get(guild.roles, name="Cursed Gambler")
        
        if not divine_role:
            divine_role = await guild.create_role(
                name="Divine Chosen",
                color=discord.Color.gold(),
                hoist=True,
                mentionable=False
            )
            
        if not cursed_role:
            cursed_role = await guild.create_role(
                name="Cursed Gambler",
                color=discord.Color.dark_red(),
                hoist=False,
                mentionable=False
            )
        
        await self.db.servers.update_one(
            {"server_id": guild.id},
            {
                "$set": {
                    "gamble_roles.divine_chosen_id": divine_role.id,
                    "gamble_roles.cursed_gambler_id": cursed_role.id
                }
            },
            upsert=True
        )
        
        return divine_role, cursed_role
        
    async def process_divine_gamble(self, interaction: discord.Interaction, amount: int):
        user_data = await self.get_user_data(interaction.user.id)
        
        current_trust = user_data.get("trust_score", 50)
        current_points = user_data.get("points", 0)
        
        if current_trust < amount:
            await interaction.response.send_message(f"❌ You need {amount} trust! You have: {current_trust}", ephemeral=True)
            return
            
        if current_points < 10:
            await interaction.response.send_message(f"❌ You need 10 points! You have: {current_points}", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": interaction.user.id},
            {
                "$inc": {
                    "points": -10,
                    "trust_score": -amount,
                    "game_stats.gamble.attempts": 1
                }
            }
        )
        
        loading_embed = discord.Embed(
            title="🎲 The dice of fate are rolling...",
            description="Your destiny is being decided...",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=loading_embed)
        await asyncio.sleep(3)
        
        roll = random.randint(1, 100)
        blessed = roll <= 5
        
        divine_role, cursed_role = await self.create_or_get_roles(interaction.guild)
        
        if blessed:
            await self.remove_divine_role_from_current(interaction.guild)
            
            server = await self.db.servers.find_one({"server_id": interaction.guild.id})
            role_config = await self.get_user_role_config(interaction.user, server) if server else {}
            
            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
            trust_return = int((amount * 3) * trust_multiplier)
            points_return = int(130 * trust_multiplier)
            
            await self.db.users.update_one(
                {"user_id": interaction.user.id},
                {
                    "$inc": {
                        "points": points_return,
                        "trust_score": trust_return,
                        "total_earned": points_return,
                        "game_stats.gamble.wins": 1
                    }
                }
            )
            
            await interaction.user.add_roles(divine_role)
            
            await self.db.divine_gambles.insert_one({
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id,
                "timestamp": datetime.now(timezone.utc),
                "status": "blessed",
                "roll": roll,
                "trust_gained": trust_return - amount,
                "points_gained": points_return - 10,
                "role_expires": datetime.now(timezone.utc) + timedelta(days=7),
                "gamble_amount": amount
            })
            
            result_embed = discord.Embed(
                title="🌟 DIVINE BLESSING!",
                description=f"{interaction.user.mention} has been chosen by the gods!",
                color=discord.Color.gold()
            )
            result_embed.add_field(
                name="🎲 Roll",
                value=f"**{roll}**/100 (needed ≤5)",
                inline=True
            )
            result_embed.add_field(
                name="💰 Rewards",
                value=f"Trust: +{trust_return - amount} net gain\nPoints: +{points_return - 10} net gain",
                inline=True
            )
            if trust_multiplier > 1.0:
                result_embed.add_field(
                    name="🎭 Role Bonus",
                    value=f"×{trust_multiplier} multiplier applied!",
                    inline=False
                )
            result_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            await interaction.edit_original_response(embed=result_embed)
            
            announce_embed = discord.Embed(
                title="🌟 NEW DIVINE CHOSEN!",
                description=f"{interaction.user.mention} has beaten the 5% odds and received divine blessing!",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            await interaction.channel.send(embed=announce_embed)
            
            await self.log_action(
                interaction.guild.id,
                f"🌟 {interaction.user.mention} won the divine gamble! (+{trust_return - amount} trust, +{points_return - 10} points)",
                discord.Color.gold()
            )
            
        else:
            await interaction.user.add_roles(cursed_role)
            
            self.bot.loop.create_task(self.remove_cursed_role(interaction.user, cursed_role, 86400))
            
            await self.db.divine_gambles.insert_one({
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id,
                "timestamp": datetime.now(timezone.utc),
                "status": "cursed",
                "roll": roll,
                "trust_lost": amount,
                "points_lost": 10,
                "gamble_amount": amount
            })
            
            result_embed = discord.Embed(
                title="💀 CURSED!",
                description="The gods have rejected your offering...",
                color=discord.Color.dark_red()
            )
            result_embed.add_field(
                name="🎲 Roll",
                value=f"**{roll}**/100 (needed ≤5)",
                inline=True
            )
            result_embed.add_field(
                name="💸 Losses",
                value=f"Trust: -{amount}\nPoints: -10",
                inline=True
            )
            result_embed.set_footer(text="Better luck next week...")
            
            await interaction.edit_original_response(embed=result_embed)
            
            await self.log_action(
                interaction.guild.id,
                f"💀 {interaction.user.mention} lost the divine gamble (-{amount} trust, -10 points)",
                discord.Color.red()
            )
            
    async def remove_cursed_role(self, member: discord.Member, role: discord.Role, delay: int):
        await asyncio.sleep(delay)
        try:
            await member.remove_roles(role)
        except:
            pass
            
    @commands.hybrid_group(name="gamble", description="Divine gambling system")
    async def gamble(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/gamble divine` to take the ultimate risk!", ephemeral=True)
            
    @gamble.command(name="divine", description="Risk it all for divine blessing (5% win chance)")
    async def gamble_divine(self, ctx):
        user_data = await self.get_user_data(ctx.author.id)
        
        requirements_met = True
        requirement_details = {}
        
        active_invites = await self.count_active_invites(ctx.author.id)
        requirement_details["invites"] = {
            "has": active_invites,
            "needs": 5,
            "met": active_invites >= 5
        }
        if not requirement_details["invites"]["met"]:
            requirements_met = False
            
        current_trust = user_data.get("trust_score", 50)
        requirement_details["trust"] = {
            "has": current_trust,
            "needs": 15,
            "met": current_trust >= 15
        }
        if not requirement_details["trust"]["met"]:
            requirements_met = False
            
        current_points = user_data.get("points", 0)
        requirement_details["points"] = {
            "has": current_points,
            "needs": 10,
            "met": current_points >= 10
        }
        if not requirement_details["points"]["met"]:
            requirements_met = False
            
        can_gamble, cooldown_end = await self.check_cooldown(ctx.author.id)
        requirement_details["cooldown"] = {
            "met": can_gamble,
            "end_time": cooldown_end
        }
        if not can_gamble:
            requirements_met = False
            
        embed = discord.Embed(
            title="🎰 DIVINE GAMBLE",
            description="**Your Current Status:**",
            color=discord.Color.gold() if requirements_met else discord.Color.red()
        )
        
        invite_text = f"You have: **{active_invites}**/5"
        if not requirement_details["invites"]["met"]:
            invite_text += " ❌"
        else:
            invite_text += " ✅"
        embed.add_field(name="👥 Active Invites", value=invite_text, inline=True)
        
        trust_text = f"You have: **{current_trust}**"
        if not requirement_details["trust"]["met"]:
            trust_text += " ❌"
        else:
            trust_text += " ✅"
        embed.add_field(name="🏆 Trust Score", value=trust_text, inline=True)
        
        points_text = f"You have: **{current_points}**/10"
        if not requirement_details["points"]["met"]:
            points_text += " ❌"
        else:
            points_text += " ✅"
        embed.add_field(name="💰 Points", value=points_text, inline=True)
        
        if not can_gamble:
            embed.add_field(
                name="⏰ Cooldown",
                value=f"Available <t:{int(cooldown_end.timestamp())}:R> ❌",
                inline=True
            )
        else:
            embed.add_field(
                name="⏰ Cooldown",
                value="Ready! ✅",
                inline=True
            )
            
        if not requirements_met:
            embed.add_field(
                name="❌ Requirements Not Met",
                value="You must meet ALL requirements to gamble!",
                inline=False
            )
            embed.color = discord.Color.red()
            await ctx.send(embed=embed, ephemeral=True)
            return
            
        embed.add_field(
            name="✅ Ready to Gamble!",
            value="Click button to choose your gamble amount (min 15 trust + 10 points)",
            inline=False
        )
        
        embed.add_field(
            name="💀 If Cursed (95% chance)",
            value="• Lose your trust gamble\n• Lose 10 points\n• Cursed role (24h)",
            inline=True
        )
        
        embed.add_field(
            name="🌟 If Blessed (5% chance)",
            value="• 3x trust return\n• +130 points return\n• Divine Chosen role",
            inline=True
        )
        
        server = await self.db.servers.find_one({"server_id": ctx.guild.id})
        role_config = await self.get_user_role_config(ctx.author, server) if server else {}
        
        if role_config and role_config.get("trust_multiplier", 1.0) > 1.0:
            multiplier = role_config["trust_multiplier"]
            embed.add_field(
                name="🎭 Your Role Bonus",
                value=f"×{multiplier} multiplier on rewards!",
                inline=False
            )
        
        embed.set_footer(text="Only the brave or desperate dare...")
        
        modal = BetAmountModal(self, ctx.author.id)
        await ctx.send_modal(modal)
            
    @gamble.command(name="stats", description="View your divine gambling statistics")
    async def gamble_stats(self, ctx):
        user_data = await self.get_user_data(ctx.author.id)
        
        stats = user_data.get("game_stats", {}).get("gamble", {})
        total_gambles = stats.get("attempts", 0)
        wins = stats.get("wins", 0)
        losses = total_gambles - wins
        
        embed = discord.Embed(
            title="🎰 Your Divine Gambling Stats",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="🎲 Total Gambles", value=str(total_gambles), inline=True)
        embed.add_field(name="🌟 Blessed", value=str(wins), inline=True)
        embed.add_field(name="💀 Cursed", value=str(losses), inline=True)
        
        if total_gambles > 0:
            win_rate = (wins / total_gambles) * 100
            embed.add_field(
                name="📊 Win Rate",
                value=f"{win_rate:.1f}% (Expected: 5%)",
                inline=True
            )
            
        can_gamble, cooldown_end = await self.check_cooldown(ctx.author.id)
        if not can_gamble:
            embed.add_field(
                name="⏰ Next Gamble",
                value=f"<t:{int(cooldown_end.timestamp())}:R>",
                inline=True
            )
        else:
            embed.add_field(
                name="⏰ Status",
                value="Ready to gamble!",
                inline=True
            )
            
        last_gamble = await self.db.divine_gambles.find_one(
            {"user_id": ctx.author.id},
            sort=[("timestamp", -1)]
        )
        
        if last_gamble:
            result = "🌟 Blessed" if last_gamble["status"] == "blessed" else "💀 Cursed"
            embed.add_field(
                name="📅 Last Gamble",
                value=f"{result}\n<t:{int(last_gamble['timestamp'].timestamp())}:R>",
                inline=False
            )
            
        embed.set_footer(text=f"Remember: Only 5% win chance!")
        await ctx.send(embed=embed, ephemeral=True)
        
    @gamble.command(name="requirements", description="Check divine gamble requirements")
    async def gamble_requirements(self, ctx):
        embed = discord.Embed(
            title="🎰 Divine Gamble Requirements",
            description="You must meet ALL requirements to gamble:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 Entry Requirements",
            value="• **Invites:** 5+ verified users (still in server)\n"
                  "• **Trust Score:** 15+ minimum to gamble\n"
                  "• **Points:** 10 (fixed cost)\n"
                  "• **Cooldown:** 7 days between gambles",
            inline=False
        )
        
        embed.add_field(
            name="💀 If Cursed (95% chance)",
            value="• Lose your trust gamble\n"
                  "• Lose 10 points permanently\n"
                  "• Get Cursed Gambler role (24h)",
            inline=True
        )
        
        embed.add_field(
            name="🌟 If Blessed (5% chance)",
            value="• Return: 3x trust gambled\n"
                  "• Return: 130 points (+120 profit)\n"
                  "• Divine Chosen role (exclusive)",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Important Notes",
            value="• You choose how much trust to gamble (min 15)\n"
                  "• Higher gamble = higher potential reward\n"
                  "• Only ONE Divine Chosen per server\n"
                  "• Role bonuses apply to rewards",
            inline=False
        )
        
        embed.set_footer(text="Gamble responsibly - the house always wins!")
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GambleCog(bot))