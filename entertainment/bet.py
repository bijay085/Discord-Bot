import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import math

class BetAmountModal(discord.ui.Modal):
    def __init__(self, bet_game, user_id: int):
        super().__init__(title="Enter Bet Amount")
        self.bet_game = bet_game
        self.user_id = user_id
        
        self.amount = discord.ui.TextInput(
            label="How much do you want to bet?",
            placeholder="Enter amount...",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.amount)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            if amount <= 0:
                await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
                return
                
            await self.bet_game.add_player_from_interaction(interaction, amount)
                
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount!", ephemeral=True)

class GuessNumberModal(discord.ui.Modal):
    def __init__(self, bet_game, user_id: int, max_number: int):
        super().__init__(title=f"Guess a number (1-{max_number})")
        self.bet_game = bet_game
        self.user_id = user_id
        self.max_number = max_number
        
        self.guess = discord.ui.TextInput(
            label=f"Your guess (1-{max_number})",
            placeholder="Enter your guess...",
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.guess)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            guess = int(self.guess.value)
            if guess < 1 or guess > self.max_number:
                await interaction.response.send_message(f"❌ Guess must be between 1-{self.max_number}!", ephemeral=True)
                return
                
            success = await self.bet_game.submit_guess(interaction.user.id, guess)
            if success:
                await interaction.response.send_message(f"✅ You guessed: {guess}", ephemeral=True)
            else:
                await interaction.response.send_message("❌ You already guessed or aren't in this bet!", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("❌ Invalid number!", ephemeral=True)

class BetView(discord.ui.View):
    def __init__(self, bet_game):
        super().__init__(timeout=300)
        self.bet_game = bet_game
        self.update_buttons()
    
    def update_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "join_bet":
                    item.disabled = self.bet_game.phase != "joining"
                elif item.custom_id == "submit_guess":
                    item.disabled = self.bet_game.phase != "guessing"
    
    @discord.ui.button(label="🎲 Join Bet", style=discord.ButtonStyle.success, custom_id="join_bet")
    async def join_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.bet_game.mode == "solo":
            if interaction.user.id != self.bet_game.host_id:
                await interaction.response.send_message("❌ This is a solo bet! Start your own with `/bet solo`", ephemeral=True)
                return
            
            if self.bet_game.phase != "joining":
                await interaction.response.send_message("❌ This bet has already started!", ephemeral=True)
                return
                
            await self.bet_game.start_solo_game(interaction)
        else:
            if interaction.user.id in self.bet_game.players:
                await interaction.response.send_message("❌ You're already in this bet!", ephemeral=True)
                return
                
            modal = BetAmountModal(self.bet_game, interaction.user.id)
            await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⏰ Manage Timer", style=discord.ButtonStyle.primary, custom_id="manage_timer")
    async def manage_timer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.bet_game.host_id:
            await interaction.response.send_message("❌ Only the host can manage timer!", ephemeral=True)
            return
        
        timer_view = TimerManageView(self.bet_game)
        await interaction.response.send_message("⏰ Timer Management:", view=timer_view, ephemeral=True)
    
    @discord.ui.button(label="📝 Submit Guess", style=discord.ButtonStyle.success, custom_id="submit_guess", disabled=True)
    async def submit_guess(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.bet_game.players:
            await interaction.response.send_message("❌ You're not in this bet!", ephemeral=True)
            return
            
        if interaction.user.id in self.bet_game.guesses:
            await interaction.response.send_message("❌ You already submitted your guess!", ephemeral=True)
            return
        
        modal = GuessNumberModal(self.bet_game, interaction.user.id, self.bet_game.max_number)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel_bet")
    async def cancel_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.bet_game.host_id:
            await interaction.response.send_message("❌ Only the host can cancel!", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self.bet_game.cancel_game()
        await interaction.followup.send("✅ Bet cancelled and refunded!", ephemeral=True)

class TimerManageView(discord.ui.View):
    def __init__(self, bet_game):
        super().__init__(timeout=60)
        self.bet_game = bet_game
    
    @discord.ui.button(label="+30s", style=discord.ButtonStyle.success)
    async def add_30(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bet_game.timer_end += timedelta(seconds=30)
        await interaction.response.send_message("⏰ Added 30 seconds!", ephemeral=True)
        await self.bet_game.update_embed()
    
    @discord.ui.button(label="+60s", style=discord.ButtonStyle.success)
    async def add_60(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bet_game.timer_end += timedelta(seconds=60)
        await interaction.response.send_message("⏰ Added 60 seconds!", ephemeral=True)
        await self.bet_game.update_embed()
    
    @discord.ui.button(label="-30s", style=discord.ButtonStyle.danger)
    async def sub_30(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.bet_game.timer_end -= timedelta(seconds=30)
        await interaction.response.send_message("⏰ Reduced 30 seconds!", ephemeral=True)
        await self.bet_game.update_embed()
    
    @discord.ui.button(label="Start Now", style=discord.ButtonStyle.primary)
    async def start_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎯 Starting game now!", ephemeral=True)
        await self.bet_game.start_guessing_phase()

class BetGame:
    def __init__(self, cog, host, mode: str, currency: str, initial_bet: int = None):
        self.cog = cog
        self.host_id = host.id
        self.mode = mode
        self.currency = currency
        self.channel = None
        self.message = None
        self.view = None
        
        self.players = {}
        self.guesses = {}
        self.phase = "joining"
        
        self.max_players = 50
        self.timer_end = datetime.now(timezone.utc) + timedelta(seconds=60)
        self.guess_timer_end = None
        self.timer_task = None
        
        self.winning_number = None
        self.max_number = 10 if mode == "solo" else 10
        
        if mode == "solo" and initial_bet:
            self.initial_bet = initial_bet
    
    async def start_solo_game(self, interaction: discord.Interaction):
        if self.phase != "joining":
            return
            
        user_data = await self.cog.get_user_data(interaction.user.id)
        amount = self.initial_bet
        
        if self.currency == "points":
            if user_data["points"] < amount:
                await interaction.response.send_message(f"❌ You need {amount} points!", ephemeral=True)
                return
            await self.cog.db.users.update_one(
                {"user_id": interaction.user.id},
                {"$inc": {"points": -amount}}
            )
        else:
            if user_data.get("trust_score", 50) < amount:
                await interaction.response.send_message(f"❌ You need {amount} trust!", ephemeral=True)
                return
            current_trust = user_data.get("trust_score", 50)
            await self.cog.db.users.update_one(
                {"user_id": interaction.user.id},
                {"$set": {"trust_score": current_trust - amount}}
            )
        
        self.players[interaction.user.id] = {"user": interaction.user, "bet": amount}
        
        await interaction.response.send_message("✅ Solo bet started! Make your guess!", ephemeral=True)
        
        self.phase = "guessing"
        self.winning_number = random.randint(1, 10)
        self.guess_timer_end = datetime.now(timezone.utc) + timedelta(seconds=30)
        
        self.view.update_buttons()
        await self.update_embed()
        
        self.cog.bot.loop.create_task(self.run_guess_timer())
    
    async def add_player_from_interaction(self, interaction: discord.Interaction, amount: int):
        if self.phase != "joining":
            await interaction.response.send_message("❌ This bet is no longer accepting players!", ephemeral=True)
            return
            
        if len(self.players) >= self.max_players:
            await interaction.response.send_message("❌ This bet is full!", ephemeral=True)
            return
        
        user_data = await self.cog.get_user_data(interaction.user.id)
        
        server = await self.cog.db.servers.find_one({"server_id": interaction.guild_id})
        role_config = await self.cog.get_user_role_config(interaction.user, server) if server else {}
        
        bet_profit_multiplier = role_config.get("game_benefits", {}).get("bet_profit_multiplier", 1.0) if role_config else 1.0
        
        if self.currency == "points":
            if user_data["points"] < amount:
                await interaction.response.send_message(f"❌ You need {amount} points! You have: {user_data['points']}", ephemeral=True)
                return
        else:
            if user_data.get("trust_score", 50) < amount:
                await interaction.response.send_message(f"❌ You need {amount} trust! You have: {user_data.get('trust_score', 50)}", ephemeral=True)
                return
        
        if self.currency == "points":
            await self.cog.db.users.update_one(
                {"user_id": interaction.user.id},
                {"$inc": {"points": -amount}}
            )
        else:
            current_trust = user_data.get("trust_score", 50)
            await self.cog.db.users.update_one(
                {"user_id": interaction.user.id},
                {"$set": {"trust_score": current_trust - amount}}
            )
        
        self.players[interaction.user.id] = {
            "user": interaction.user, 
            "bet": amount,
            "profit_multiplier": bet_profit_multiplier
        }
        
        if self.mode == "group":
            self.max_number = 10 + (len(self.players) * 2)
        
        response_text = f"✅ Joined with {amount} {self.currency}!"
        if bet_profit_multiplier > 1.0:
            response_text += f"\n🎭 Role bonus: {bet_profit_multiplier}x profit multiplier!"
        
        await interaction.response.send_message(response_text, ephemeral=True)
        await self.update_embed()
        
        if len(self.players) >= self.max_players:
            await self.start_guessing_phase()
    
    async def add_player(self, user, amount: int) -> bool:
        if self.phase != "joining":
            return False
            
        if len(self.players) >= self.max_players:
            return False
        
        user_data = await self.cog.get_user_data(user.id)
        if self.currency == "points":
            if user_data["points"] < amount:
                return False
        else:
            if user_data.get("trust_score", 50) < amount:
                return False
        
        if self.currency == "points":
            await self.cog.db.users.update_one(
                {"user_id": user.id},
                {"$inc": {"points": -amount}}
            )
        else:
            current_trust = user_data.get("trust_score", 50)
            await self.cog.db.users.update_one(
                {"user_id": user.id},
                {"$set": {"trust_score": current_trust - amount}}
            )
        
        self.players[user.id] = {"user": user, "bet": amount}
        
        if self.mode == "group":
            self.max_number = 10 + (len(self.players) * 2)
        
        await self.update_embed()
        
        if len(self.players) >= self.max_players:
            await self.start_guessing_phase()
        
        return True
    
    async def submit_guess(self, user_id: int, guess: int) -> bool:
        if self.phase != "guessing":
            return False
            
        if user_id not in self.players:
            return False
            
        if user_id in self.guesses:
            return False
        
        self.guesses[user_id] = guess
        
        await self.update_embed()
        
        if len(self.guesses) == len(self.players):
            await self.end_game()
        
        return True
    
    async def start_guessing_phase(self):
        if self.phase != "joining":
            return
            
        self.phase = "guessing"
        self.winning_number = random.randint(1, self.max_number)
        self.guess_timer_end = datetime.now(timezone.utc) + timedelta(seconds=30)
        
        self.view.update_buttons()
        
        await self.update_embed()
        
        if self.timer_task:
            self.timer_task.cancel()
        
        self.cog.bot.loop.create_task(self.run_guess_timer())
    
    async def run_guess_timer(self):
        await asyncio.sleep(30)
        if self.phase == "guessing":
            await self.end_game()
    
    async def end_game(self):
        if self.phase == "ended":
            return
            
        self.phase = "ended"
        
        if self.timer_task:
            self.timer_task.cancel()
        
        winner = None
        closest_diff = float('inf')
        
        for user_id, guess in self.guesses.items():
            diff = abs(guess - self.winning_number)
            if diff < closest_diff:
                closest_diff = diff
                winner = user_id
        
        embed = discord.Embed(
            title="🎲 Bet Results!",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="🎯 Winning Number", value=str(self.winning_number), inline=True)
        embed.add_field(name="💰 Currency", value=self.currency.title(), inline=True)
        embed.add_field(name="👥 Players", value=str(len(self.players)), inline=True)
        
        if winner and closest_diff == 0:
            winner_data = self.players[winner]
            profit_multiplier = winner_data.get("profit_multiplier", 1.0)
            base_profit = winner_data["bet"] * 0.5
            actual_profit = base_profit * profit_multiplier
            total_win = winner_data["bet"] + actual_profit
            
            if self.currency == "points":
                await self.cog.db.users.update_one(
                    {"user_id": winner},
                    {
                        "$inc": {
                            "points": int(total_win),
                            "game_stats.bet.won": 1,
                            "game_stats.bet.profit": int(actual_profit)
                        }
                    }
                )
            else:
                user_data = await self.cog.get_user_data(winner)
                new_trust = user_data.get("trust_score", 50) + total_win
                await self.cog.db.users.update_one(
                    {"user_id": winner},
                    {
                        "$set": {"trust_score": min(100, new_trust)},
                        "$inc": {
                            "game_stats.bet.won": 1,
                            "game_stats.bet.profit": int(actual_profit)
                        }
                    }
                )
            
            winner_text = f"{winner_data['user'].mention} guessed correctly!\n"
            winner_text += f"Bet: {winner_data['bet']} → Won: {int(total_win)} (+{int(actual_profit)})"
            if profit_multiplier > 1.0:
                winner_text += f"\n🎭 Role bonus applied: {profit_multiplier}x"
            
            embed.add_field(
                name="🏆 Winner!",
                value=winner_text,
                inline=False
            )
            
            await self.cog.log_action(
                self.channel.guild.id,
                f"🎲 {winner_data['user'].mention} won {int(total_win)} {self.currency} in bet!",
                discord.Color.green()
            )
        
        elif winner and self.mode == "group":
            winner_data = self.players[winner]
            consolation = int(winner_data["bet"] * 0.5)
            
            if self.currency == "points":
                await self.cog.db.users.update_one(
                    {"user_id": winner},
                    {"$inc": {"points": consolation}}
                )
            else:
                user_data = await self.cog.get_user_data(winner)
                new_trust = user_data.get("trust_score", 50) + consolation
                await self.cog.db.users.update_one(
                    {"user_id": winner},
                    {"$set": {"trust_score": min(100, new_trust)}}
                )
            
            embed.add_field(
                name="🥈 Closest Guess",
                value=f"{winner_data['user'].mention} (guessed {self.guesses.get(winner, 'N/A')})\n"
                      f"Consolation: {consolation} {self.currency} (50% back)",
                inline=False
            )
        
        elif winner and self.mode == "solo" and closest_diff <= 2:
            player_data = self.players[self.host_id]
            consolation = int(player_data["bet"] * 0.15)
            
            if self.currency == "points":
                await self.cog.db.users.update_one(
                    {"user_id": self.host_id},
                    {"$inc": {"points": consolation}}
                )
            else:
                user_data = await self.cog.get_user_data(self.host_id)
                new_trust = user_data.get("trust_score", 50) + consolation
                await self.cog.db.users.update_one(
                    {"user_id": self.host_id},
                    {"$set": {"trust_score": min(100, new_trust)}}
                )
            
            embed.add_field(
                name="😅 Close Guess!",
                value=f"You guessed {self.guesses.get(self.host_id, 'N/A')}\n"
                      f"Consolation: {consolation} {self.currency} (15% back)",
                inline=False
            )
        else:
            embed.add_field(
                name="😢 No Winners",
                value="Nobody guessed correctly or submitted a guess!",
                inline=False
            )
        
        for user_id, player_data in self.players.items():
            if user_id not in self.guesses or (winner and user_id == winner):
                continue
            await self.cog.db.users.update_one(
                {"user_id": user_id},
                {"$inc": {"game_stats.bet.played": 1}}
            )
        
        if self.guesses:
            guess_list = []
            for user_id, guess in sorted(self.guesses.items(), key=lambda x: abs(x[1] - self.winning_number)):
                player = self.players[user_id]
                diff = abs(guess - self.winning_number)
                guess_list.append(f"{player['user'].mention}: {guess} (diff: {diff})")
            
            embed.add_field(
                name="📊 All Guesses",
                value="\n".join(guess_list[:10]),
                inline=False
            )
        
        for item in self.view.children:
            item.disabled = True
        
        await self.message.edit(embed=embed, view=self.view)
        
        if self.channel.id in self.cog.active_games:
            del self.cog.active_games[self.channel.id]
    
    async def cancel_game(self):
        if self.phase == "ended":
            return
            
        self.phase = "ended"
        
        if self.timer_task:
            self.timer_task.cancel()
        
        for user_id, player_data in self.players.items():
            if self.currency == "points":
                await self.cog.db.users.update_one(
                    {"user_id": user_id},
                    {"$inc": {"points": player_data["bet"]}}
                )
            else:
                user_data = await self.cog.get_user_data(user_id)
                new_trust = user_data.get("trust_score", 50) + player_data["bet"]
                await self.cog.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"trust_score": min(100, new_trust)}}
                )
        
        embed = discord.Embed(
            title="❌ Bet Cancelled",
            description="All bets have been refunded!",
            color=discord.Color.red()
        )
        
        for item in self.view.children:
            item.disabled = True
        
        await self.message.edit(embed=embed, view=self.view)
        
        if self.channel.id in self.cog.active_games:
            del self.cog.active_games[self.channel.id]
    
    async def update_embed(self):
        if not self.message:
            return
        
        if self.phase == "joining":
            embed = discord.Embed(
                title=f"🎲 {self.mode.title()} Bet",
                description=f"Currency: **{self.currency.title()}**",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if self.players:
                player_list = []
                total_pool = sum(p["bet"] for p in self.players.values())
                
                for user_id, player_data in self.players.items():
                    percentage = (player_data["bet"] / total_pool * 100) if total_pool > 0 else 0
                    multiplier = player_data.get("profit_multiplier", 1.0)
                    player_text = f"{player_data['user'].mention}: {player_data['bet']} ({percentage:.1f}%)"
                    if multiplier > 1.0:
                        player_text += f" 🎭×{multiplier}"
                    player_list.append(player_text)
                
                embed.add_field(
                    name=f"👥 Players ({len(self.players)}/{self.max_players})",
                    value="\n".join(player_list[:10]) + ("\n..." if len(player_list) > 10 else ""),
                    inline=False
                )
                embed.add_field(name="💰 Total Pool", value=str(total_pool), inline=True)
            
            time_left = max(0, (self.timer_end - datetime.now(timezone.utc)).total_seconds())
            embed.add_field(name="⏰ Time Left", value=f"{int(time_left)}s", inline=True)
            
        elif self.phase == "guessing":
            embed = discord.Embed(
                title="🎯 Make Your Guess!",
                description=f"Guess a number between **1-{self.max_number}**",
                color=discord.Color.gold()
            )
            
            embed.add_field(
                name="👥 Guessed",
                value=f"{len(self.guesses)}/{len(self.players)}",
                inline=True
            )
            
            if self.guess_timer_end:
                time_left = max(0, (self.guess_timer_end - datetime.now(timezone.utc)).total_seconds())
                embed.add_field(name="⏰ Time Left", value=f"{int(time_left)}s", inline=True)
            
            total_pool = sum(p["bet"] for p in self.players.values())
            embed.add_field(name="💰 Pool", value=str(total_pool), inline=True)
        
        try:
            await self.message.edit(embed=embed, view=self.view)
        except:
            pass

class BetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.active_games = {}
        self.cleanup_games.start()
    
    async def cog_load(self):
        print("🎮 BetCog loaded")
    
    async def get_user_data(self, user_id: int):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "points": 0,
                "trust_score": 50,
                "game_stats": {
                    "bet": {"played": 0, "won": 0, "profit": 0}
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
    
    @tasks.loop(minutes=5)
    async def cleanup_games(self):
        to_remove = []
        for channel_id, game in self.active_games.items():
            if game.phase == "ended":
                to_remove.append(channel_id)
        
        for channel_id in to_remove:
            del self.active_games[channel_id]
    
    @cleanup_games.before_loop
    async def before_cleanup_games(self):
        await self.bot.wait_until_ready()
    
    @commands.hybrid_command(name="bet", description="Start a betting game!")
    @app_commands.describe(
        mode="Solo (vs bot) or Group (multiplayer)",
        currency="Bet with points or trust score",
        amount="Amount to bet (solo mode only)"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Solo", value="solo"),
            app_commands.Choice(name="Group", value="group")
        ],
        currency=[
            app_commands.Choice(name="Points", value="points"),
            app_commands.Choice(name="Trust Score", value="trust")
        ]
    )
    async def bet(self, ctx, mode: str, currency: str, amount: Optional[int] = None):
        if ctx.channel.id in self.active_games:
            await ctx.send("❌ A bet is already active in this channel!", ephemeral=True)
            return
        
        if mode == "solo" and not amount:
            await ctx.send("❌ Please specify an amount for solo bet!", ephemeral=True)
            return
        
        if amount and amount <= 0:
            await ctx.send("❌ Bet amount must be positive!", ephemeral=True)
            return
        
        if mode == "solo" and amount:
            user_data = await self.get_user_data(ctx.author.id)
            if currency == "points":
                if user_data["points"] < amount:
                    await ctx.send(f"❌ You need {amount} points! You have: {user_data['points']}", ephemeral=True)
                    return
            else:
                if user_data.get("trust_score", 50) < amount:
                    await ctx.send(f"❌ You need {amount} trust! You have: {user_data.get('trust_score', 50)}", ephemeral=True)
                    return
        
        game = BetGame(self, ctx.author, mode, currency, amount)
        game.channel = ctx.channel
        
        server = await self.db.servers.find_one({"server_id": ctx.guild.id})
        role_config = await self.get_user_role_config(ctx.author, server) if server else {}
        
        if mode == "solo":
            embed = discord.Embed(
                title="🎲 Solo Bet Started!",
                description=f"Betting **{amount} {currency}**\nClick button to confirm and start!",
                color=discord.Color.blue()
            )
            embed.add_field(name="🎯 Range", value="1-10", inline=True)
            embed.add_field(name="💰 Win", value=f"+{int(amount * 0.5)} profit", inline=True)
            embed.add_field(name="😅 Close Guess", value="15% back", inline=True)
            
            if role_config and role_config.get("game_benefits", {}).get("bet_profit_multiplier", 1.0) > 1.0:
                multiplier = role_config["game_benefits"]["bet_profit_multiplier"]
                embed.add_field(
                    name="🎭 Role Bonus",
                    value=f"×{multiplier} profit multiplier",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title="🎰 Group Bet Created!",
                description=f"Currency: **{currency.title()}**\nClick to join with any amount!",
                color=discord.Color.blue()
            )
            embed.add_field(name="👥 Players", value="0/50", inline=True)
            embed.add_field(name="⏰ Timer", value="60s", inline=True)
            embed.add_field(name="💰 Profit", value="50% on win", inline=True)
            
            if role_config and role_config.get("game_benefits", {}).get("bet_profit_multiplier", 1.0) > 1.0:
                multiplier = role_config["game_benefits"]["bet_profit_multiplier"]
                embed.add_field(
                    name="🎭 Your Role Bonus",
                    value=f"×{multiplier} profit multiplier",
                    inline=False
                )
        
        embed.set_footer(text="Click buttons below to interact!")
        
        view = BetView(game)
        game.view = view
        
        message = await ctx.send(embed=embed, view=view)
        game.message = message
        
        self.active_games[ctx.channel.id] = game
        
        await self.db.users.update_one(
            {"user_id": ctx.author.id},
            {"$inc": {"game_stats.bet.played": 1}}
        )
        
        if mode == "group":
            game.timer_task = self.bot.loop.create_task(self._run_join_timer(game))
    
    async def _run_join_timer(self, game):
        await asyncio.sleep(60)
        if game.phase == "joining":
            if len(game.players) > 0:
                await game.start_guessing_phase()
            else:
                await game.cancel_game()

async def setup(bot):
    await bot.add_cog(BetCog(bot))
    print("✅ BetCog loaded successfully!")