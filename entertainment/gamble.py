import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

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
        """Remove expired Divine Chosen roles"""
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
        
    async def get_or_create_user(self, user_id: int, username: str):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "username": username,
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
                "last_claim": None,
                "cookie_claims": {},
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
                    "divine_losses": 0
                }
            }
            await self.db.users.insert_one(user)
        else:
            await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_active": datetime.now(timezone.utc)}}
            )
        return user
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
            
    async def count_active_invites(self, user_id: int) -> int:
        """Count how many invited users are still in the server"""
        user_data = await self.db.users.find_one({"user_id": user_id})
        if not user_data:
            return 0
            
        active_count = 0
        for invited_user in user_data.get("invited_users", []):
            if invited_user.get("verified", False):
                active_count += 1
                
        return active_count
        
    async def check_cooldown(self, user_id: int) -> tuple[bool, Optional[datetime]]:
        """Check if user is on cooldown"""
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
        """Remove Divine Chosen role from current holder"""
        divine_role = discord.utils.get(guild.roles, name="Divine Chosen")
        if divine_role:
            for member in divine_role.members:
                await member.remove_roles(divine_role)
                # Update database
                await self.db.divine_gambles.update_many(
                    {"guild_id": guild.id, "user_id": member.id, "status": "blessed"},
                    {"$set": {"role_removed": True}}
                )
                
    async def create_or_get_roles(self, guild: discord.Guild):
        """Create necessary roles if they don't exist and save to database"""
        divine_role = None
        cursed_role = None
        
        # First, check if server has saved role IDs
        server_data = await self.db.servers.find_one({"server_id": guild.id})
        
        if server_data and server_data.get("gamble_roles"):
            # Try to get roles by saved IDs
            divine_role_id = server_data["gamble_roles"].get("divine_chosen_id")
            cursed_role_id = server_data["gamble_roles"].get("cursed_gambler_id")
            
            if divine_role_id:
                divine_role = guild.get_role(divine_role_id)
            if cursed_role_id:
                cursed_role = guild.get_role(cursed_role_id)
        
        # If not found by ID, try to find by name
        if not divine_role:
            divine_role = discord.utils.get(guild.roles, name="Divine Chosen")
        
        if not cursed_role:
            cursed_role = discord.utils.get(guild.roles, name="Cursed Gambler")
        
        # Create roles if they still don't exist
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
        
        # Save/update role IDs in database
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
        
    @commands.hybrid_group(name="gamble", description="Divine gambling system")
    async def gamble(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/gamble divine` to take the ultimate risk!", ephemeral=True)
            
    @gamble.command(name="divine", description="Risk it all for divine blessing (5% win chance)")
    async def gamble_divine(self, ctx):
        user_data = await self.get_or_create_user(ctx.author.id, str(ctx.author))
        
        # Check requirements
        requirements_met = True
        requirement_details = {}
        
        # Check invites
        active_invites = await self.count_active_invites(ctx.author.id)
        requirement_details["invites"] = {
            "has": active_invites,
            "needs": 5,
            "met": active_invites >= 5
        }
        if not requirement_details["invites"]["met"]:
            requirements_met = False
            
        # Check trust score
        current_trust = user_data.get("trust_score", 50)
        requirement_details["trust"] = {
            "has": current_trust,
            "needs": 60,
            "met": current_trust >= 60
        }
        if not requirement_details["trust"]["met"]:
            requirements_met = False
            
        # Check points
        current_points = user_data.get("points", 0)
        requirement_details["points"] = {
            "has": current_points,
            "needs": 20,
            "met": current_points >= 20
        }
        if not requirement_details["points"]["met"]:
            requirements_met = False
            
        # Check cooldown
        can_gamble, cooldown_end = await self.check_cooldown(ctx.author.id)
        requirement_details["cooldown"] = {
            "met": can_gamble,
            "end_time": cooldown_end
        }
        if not can_gamble:
            requirements_met = False
            
        # Show current status with requirements
        embed = discord.Embed(
            title="🎰 DIVINE GAMBLE",
            description="**Your Current Status:**",
            color=discord.Color.gold() if requirements_met else discord.Color.red()
        )
        
        # Invites
        invite_text = f"You have: **{active_invites}**/5"
        if not requirement_details["invites"]["met"]:
            invite_text += " ❌"
        else:
            invite_text += " ✅"
        embed.add_field(name="👥 Active Invites", value=invite_text, inline=True)
        
        # Trust
        trust_text = f"You have: **{current_trust}**/60"
        if not requirement_details["trust"]["met"]:
            trust_text += " ❌"
        else:
            trust_text += " ✅"
        embed.add_field(name="🏆 Trust Score", value=trust_text, inline=True)
        
        # Points
        points_text = f"You have: **{current_points}**/20"
        if not requirement_details["points"]["met"]:
            points_text += " ❌"
        else:
            points_text += " ✅"
        embed.add_field(name="💰 Points", value=points_text, inline=True)
        
        # Cooldown
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
            
        # All requirements met - show gamble details
        embed.add_field(
            name="✅ Ready to Gamble!",
            value="**Entry Cost:** 15 trust + 10 points (non-refundable)",
            inline=False
        )
        
        embed.add_field(
            name="💀 If Cursed (95% chance)",
            value="• Lose 15 trust\n• Lose 10 points\n• Cursed role (24h)",
            inline=True
        )
        
        embed.add_field(
            name="🌟 If Blessed (5% chance)",
            value="• +45 trust return\n• +130 points return\n• Divine Chosen role",
            inline=True
        )
        
        embed.add_field(
            name="📊 After Gamble Balance",
            value=f"**If Cursed:** {current_trust - 15} trust, {current_points - 10} points\n"
                  f"**If Blessed:** {current_trust + 30} trust, {current_points + 120} points",
            inline=False
        )
        
        embed.set_footer(text="Only the brave or desperate dare...")
        
        view = GambleView(ctx.author.id)
        message = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.choice != "confirmed":
            await message.edit(
                content="❌ Gamble cancelled. A wise choice perhaps...",
                embed=None,
                view=None
            )
            return
            
        # Process the gamble
        loading_embed = discord.Embed(
            title="🎲 The dice of fate are rolling...",
            description="Your destiny is being decided...",
            color=discord.Color.yellow()
        )
        await message.edit(embed=loading_embed, view=None)
        await asyncio.sleep(3)
        
        # Deduct entry costs immediately
        await self.db.users.update_one(
            {"user_id": ctx.author.id},
            {
                "$inc": {
                    "points": -10,
                    "trust_score": -15,
                    "statistics.divine_gambles": 1
                }
            }
        )
        
        # Roll the dice (5% win chance)
        roll = random.randint(1, 100)
        blessed = roll <= 5
        
        # Create roles if needed
        divine_role, cursed_role = await self.create_or_get_roles(ctx.guild)
        
        if blessed:
            # BLESSED!
            # Remove role from current holder
            await self.remove_divine_role_from_current(ctx.guild)
            
            # Give rewards
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$inc": {
                        "points": 130,  # Return 130 total
                        "trust_score": 45,  # Return 45 total
                        "total_earned": 130,
                        "statistics.divine_wins": 1
                    }
                }
            )
            
            # Add role
            await ctx.author.add_roles(divine_role)
            
            # Record gamble
            await self.db.divine_gambles.insert_one({
                "user_id": ctx.author.id,
                "guild_id": ctx.guild.id,
                "timestamp": datetime.now(timezone.utc),
                "status": "blessed",
                "roll": roll,
                "trust_gained": 30,  # Net gain
                "points_gained": 120,  # Net gain
                "role_expires": datetime.now(timezone.utc) + timedelta(days=7)
            })
            
            # Create result embed
            result_embed = discord.Embed(
                title="🌟 DIVINE BLESSING!",
                description=f"{ctx.author.mention} has been chosen by the gods!",
                color=discord.Color.gold()
            )
            result_embed.add_field(
                name="🎲 Roll",
                value=f"**{roll}**/100 (needed ≤5)",
                inline=True
            )
            result_embed.add_field(
                name="💰 Rewards",
                value=f"Trust: +30 net gain\nPoints: +120 net gain",
                inline=True
            )
            result_embed.set_thumbnail(url=ctx.author.display_avatar.url)
            
            await message.edit(embed=result_embed)
            
            # Public announcement
            announce_embed = discord.Embed(
                title="🌟 NEW DIVINE CHOSEN!",
                description=f"{ctx.author.mention} has beaten the 5% odds and received divine blessing!",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            await ctx.channel.send(embed=announce_embed)
            
            # Log
            await self.log_action(
                ctx.guild.id,
                f"🌟 {ctx.author.mention} won the divine gamble! (+30 trust, +120 points)",
                discord.Color.gold()
            )
            
        else:
            # CURSED!
            # Add cursed role
            await ctx.author.add_roles(cursed_role)
            
            # Schedule role removal after 24h
            self.bot.loop.create_task(self.remove_cursed_role(ctx.author, cursed_role, 86400))
            
            # Update stats
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$inc": {
                        "statistics.divine_losses": 1
                    }
                }
            )
            
            # Record gamble
            await self.db.divine_gambles.insert_one({
                "user_id": ctx.author.id,
                "guild_id": ctx.guild.id,
                "timestamp": datetime.now(timezone.utc),
                "status": "cursed",
                "roll": roll,
                "trust_lost": 15,
                "points_lost": 10
            })
            
            # Create result embed
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
                value=f"Trust: -15\nPoints: -10",
                inline=True
            )
            result_embed.set_footer(text="Better luck next week...")
            
            await message.edit(embed=result_embed)
            
            # Log
            await self.log_action(
                ctx.guild.id,
                f"💀 {ctx.author.mention} lost the divine gamble (-15 trust, -10 points)",
                discord.Color.red()
            )
            
    async def remove_cursed_role(self, member: discord.Member, role: discord.Role, delay: int):
        """Remove cursed role after delay"""
        await asyncio.sleep(delay)
        try:
            await member.remove_roles(role)
        except:
            pass
            
    @gamble.command(name="stats", description="View your divine gambling statistics")
    async def gamble_stats(self, ctx):
        user_data = await self.get_or_create_user(ctx.author.id, str(ctx.author))
        
        stats = user_data.get("statistics", {})
        total_gambles = stats.get("divine_gambles", 0)
        wins = stats.get("divine_wins", 0)
        losses = stats.get("divine_losses", 0)
        
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
            
            net_trust = (wins * 30) - (losses * 15)
            net_points = (wins * 120) - (losses * 10)
            embed.add_field(
                name="💰 Net Profit/Loss",
                value=f"Trust: {net_trust:+d}\nPoints: {net_points:+d}",
                inline=True
            )
            
        # Check cooldown
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
            
        # Last gamble info
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
                  "• **Trust Score:** 60+ (15 deducted on entry)\n"
                  "• **Points:** 20+ (10 deducted on entry)\n"
                  "• **Cooldown:** 7 days between gambles",
            inline=False
        )
        
        embed.add_field(
            name="💀 If Cursed (95% chance)",
            value="• Lose 15 trust permanently\n"
                  "• Lose 10 points permanently\n"
                  "• Get Cursed Gambler role (24h)",
            inline=True
        )
        
        embed.add_field(
            name="🌟 If Blessed (5% chance)",
            value="• Return: 45 trust (+30 profit)\n"
                  "• Return: 130 points (+120 profit)\n"
                  "• Divine Chosen role (exclusive)",
            inline=True
        )
        
        embed.add_field(
            name="⚠️ Important Notes",
            value="• Entry costs are NON-REFUNDABLE\n"
                  "• Only ONE Divine Chosen per server\n"
                  "• Role lasts until someone new wins (max 7 days)\n"
                  "• This is designed to be a NET LOSS activity",
            inline=False
        )
        
        embed.set_footer(text="Gamble responsibly - the house always wins!")
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GambleCog(bot))