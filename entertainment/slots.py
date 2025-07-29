import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Tuple

class SlotsView(discord.ui.View):
    def __init__(self, user_id: int, bet: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet = bet
        self.result = None
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your slot machine!", ephemeral=True)
            return False
        return True
        
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class SlotsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.user_cooldowns = {}
        
        self.symbols = {
            "🍒": {"name": "Cherry", "payout": 1.5, "weight": 20},
            "🍋": {"name": "Lemon", "payout": 2, "weight": 10},
            "🍊": {"name": "Orange", "payout": 3, "weight": 5},
            "🍇": {"name": "Grapes", "payout": 5, "weight": 3},
            "💎": {"name": "Diamond", "payout": 10, "weight": 1},
            "7️⃣": {"name": "Seven", "payout": 50, "weight": 0.2}
        }
        
        self.total_weight = sum(s["weight"] for s in self.symbols.values())
        self.lose_weight = 100 - self.total_weight
        self.cleanup_cooldowns.start()
        
    async def cog_load(self):
        print("🎮 SlotsCog loaded")
        
    async def cog_unload(self):
        self.cleanup_cooldowns.cancel()
        self.user_cooldowns.clear()

    @tasks.loop(hours=1)
    async def cleanup_cooldowns(self):
        now = datetime.now(timezone.utc)
        to_remove = []
        for user_id, last_spin in self.user_cooldowns.items():
            if (now - last_spin).total_seconds() > 3600:
                to_remove.append(user_id)
        for user_id in to_remove:
            del self.user_cooldowns[user_id]

    @cleanup_cooldowns.before_loop
    async def before_cleanup_cooldowns(self):
        await self.bot.wait_until_ready()
        
    async def get_user_data(self, user_id: int):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "points": 0,
                "trust_score": 50,
                "statistics": {
                    "slots_played": 0,
                    "slots_won": 0,
                    "slots_lost": 0,
                    "slots_profit": 0,
                    "slots_biggest_win": 0,
                    "slots_current_streak": 0,
                    "slots_best_streak": 0
                },
                "game_stats": {
                    "slots": {"played": 0, "won": 0, "profit": 0}
                }
            }
        else:
            # Ensure statistics field exists
            if "statistics" not in user:
                user["statistics"] = {
                    "slots_played": 0,
                    "slots_won": 0,
                    "slots_lost": 0,
                    "slots_profit": 0,
                    "slots_biggest_win": 0,
                    "slots_current_streak": 0,
                    "slots_best_streak": 0
                }
            # Ensure game_stats field exists
            if "game_stats" not in user:
                user["game_stats"] = {
                    "slots": {"played": 0, "won": 0, "profit": 0}
                }
            elif "slots" not in user.get("game_stats", {}):
                user["game_stats"]["slots"] = {"played": 0, "won": 0, "profit": 0}
                
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
            
    def check_cooldown(self, user_id: int) -> bool:
        now = datetime.now(timezone.utc)
        if user_id in self.user_cooldowns:
            last_spin = self.user_cooldowns[user_id]
            if (now - last_spin).total_seconds() < 10:
                return False
        return True
        
    def spin_slots(self) -> Tuple[List[str], Optional[str], float]:
        roll = random.uniform(0, 100)
        
        cumulative = 0
        winning_symbol = None
        
        for symbol, data in self.symbols.items():
            cumulative += data["weight"]
            if roll <= cumulative:
                winning_symbol = symbol
                break
        
        if winning_symbol:
            reels = [winning_symbol, winning_symbol, winning_symbol]
            payout = self.symbols[winning_symbol]["payout"]
        else:
            all_symbols = list(self.symbols.keys())
            reels = []
            
            for i in range(3):
                reels.append(random.choice(all_symbols))
            
            if reels[0] == reels[1] == reels[2]:
                available = [s for s in all_symbols if s != reels[0]]
                reels[2] = random.choice(available)
            
            payout = 0
            
        return reels, winning_symbol, payout
        
    async def create_spin_animation(self, message: discord.Message, bet: int) -> Tuple[List[str], Optional[str], float]:
        embed = discord.Embed(
            title="🎰 SPINNING...",
            description="```\n[ 🔄 ][ 🔄 ][ 🔄 ]\n```",
            color=discord.Color.yellow()
        )
        embed.add_field(name="💰 Bet", value=f"{bet} points", inline=True)
        await message.edit(embed=embed)
        
        reels, winning_symbol, payout = self.spin_slots()
        
        await asyncio.sleep(1)
        embed.description = f"```\n[ {reels[0]} ][ 🔄 ][ 🔄 ]\n```"
        await message.edit(embed=embed)
        
        await asyncio.sleep(1)
        embed.description = f"```\n[ {reels[0]} ][ {reels[1]} ][ 🔄 ]\n```"
        await message.edit(embed=embed)
        
        await asyncio.sleep(1)
        return reels, winning_symbol, payout
        
    @commands.hybrid_group(name="slots", description="Slot machine game")
    async def slots(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/slots play <amount>` to play!", ephemeral=True)
    
    @slots.command(name="play", description="Play the slot machine!")
    @app_commands.describe(bet="Amount to bet (min: 5, max: 200)")
    async def slots_play(self, ctx, bet: int):
        if not self.check_cooldown(ctx.author.id):
            await ctx.send("⏰ Please wait 10 seconds between spins!", ephemeral=True)
            return
            
        if bet < 5:
            await ctx.send("❌ Minimum bet is 5 points!", ephemeral=True)
            return
            
        user_data = await self.get_user_data(ctx.author.id)
        
        server = await self.db.servers.find_one({"server_id": ctx.guild.id})
        role_config = await self.get_user_role_config(ctx.author, server) if server else {}
        
        max_bet_bonus = role_config.get("game_benefits", {}).get("slots_max_bet_bonus", 0) if role_config else 0
        actual_max_bet = 200 + max_bet_bonus
        
        if bet > actual_max_bet:
            await ctx.send(f"❌ Your maximum bet is {actual_max_bet} points!", ephemeral=True)
            return
        
        if user_data["points"] < bet:
            embed = discord.Embed(
                title="❌ Insufficient Points",
                description=f"You need **{bet}** points to play!",
                color=discord.Color.red()
            )
            embed.add_field(name="Your Balance", value=f"{user_data['points']} points", inline=True)
            embed.add_field(name="Needed", value=f"{bet - user_data['points']} more", inline=True)
            await ctx.send(embed=embed, ephemeral=True)
            return
            
        if bet > user_data["points"] * 0.25 and user_data["points"] > 100:
            max_bet = int(user_data["points"] * 0.25)
            await ctx.send(f"❌ You can only bet up to 25% of your balance ({max_bet} points)!", ephemeral=True)
            return
            
        self.user_cooldowns[ctx.author.id] = datetime.now(timezone.utc)
        
        await self.db.users.update_one(
            {"user_id": ctx.author.id},
            {"$inc": {"points": -bet}}
        )
        
        embed = discord.Embed(
            title="🎰 SLOT MACHINE",
            description="```\n[ ? ][ ? ][ ? ]\n```",
            color=discord.Color.blue()
        )
        embed.add_field(name="💰 Bet", value=f"{bet} points", inline=True)
        embed.add_field(name="💵 Balance", value=f"{user_data['points'] - bet} points", inline=True)
        
        if max_bet_bonus > 0:
            embed.add_field(name="🎭 Role Bonus", value=f"+{max_bet_bonus} max bet", inline=True)
        
        embed.set_footer(text=f"Player: {ctx.author.name}")
        
        view = SlotsView(ctx.author.id, bet)
        
        message = await ctx.send(embed=embed, view=view)
        
        reels, winning_symbol, payout = await self.create_spin_animation(message, bet)
        
        winnings = int(bet * payout) if payout > 0 else 0
        profit = winnings - bet
        
        if winnings > 0:
            # Update user statistics
            current_streak = user_data.get("statistics", {}).get("slots_current_streak", 0) + 1
            best_streak = user_data.get("statistics", {}).get("slots_best_streak", 0)
            biggest_win = user_data.get("statistics", {}).get("slots_biggest_win", 0)
            
            update_dict = {
                "$inc": {
                    "points": winnings,
                    "total_earned": winnings,
                    "statistics.slots_played": 1,
                    "statistics.slots_won": 1,
                    "statistics.slots_profit": profit,
                    "game_stats.slots.played": 1,
                    "game_stats.slots.won": 1,
                    "game_stats.slots.profit": profit
                },
                "$set": {
                    "statistics.slots_current_streak": current_streak
                }
            }
            
            # Update biggest win if necessary
            if winnings > biggest_win:
                update_dict["$set"]["statistics.slots_biggest_win"] = winnings
                
            # Update best streak if necessary
            if current_streak > best_streak:
                update_dict["$set"]["statistics.slots_best_streak"] = current_streak
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                update_dict
            )
            
            symbol_name = self.symbols[winning_symbol]["name"]
            embed = discord.Embed(
                title=f"🎉 WINNER - {symbol_name.upper()}!",
                description=f"```\n[ {reels[0]} ][ {reels[1]} ][ {reels[2]} ]\n```",
                color=discord.Color.green()
            )
            embed.add_field(name="💰 Bet", value=f"{bet} points", inline=True)
            embed.add_field(name="🎯 Multiplier", value=f"{payout}x", inline=True)
            embed.add_field(name="💵 Won", value=f"**{winnings}** points", inline=True)
            embed.add_field(name="📈 Profit", value=f"+{profit} points", inline=True)
            embed.add_field(name="💳 New Balance", value=f"{user_data['points'] - bet + winnings} points", inline=True)
            embed.add_field(name="🔥 Win Streak", value=f"{current_streak}", inline=True)
            
            if payout >= 10:
                embed.set_footer(text="🎊 BIG WIN! 🎊")
            if winning_symbol == "7️⃣":
                embed.set_footer(text="💎 JACKPOT! 💎")
                
            if winnings >= 500:
                await self.log_action(
                    ctx.guild.id,
                    f"🎰 {ctx.author.mention} hit **{symbol_name}** on slots and won **{winnings}** points!",
                    discord.Color.gold()
                )
            
            await self.db.statistics.update_one(
                {"_id": "global_stats"},
                {
                    "$inc": {
                        "game_stats.slots_played": 1,
                        "game_stats.slots_won": 1
                    }
                }
            )
                
        else:
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {
                    "$inc": {
                        "statistics.slots_played": 1,
                        "statistics.slots_lost": 1,
                        "statistics.slots_profit": -bet,
                        "game_stats.slots.played": 1,
                        "game_stats.slots.profit": -bet
                    },
                    "$set": {
                        "statistics.slots_current_streak": 0
                    }
                }
            )
            
            embed = discord.Embed(
                title="💔 NO MATCH",
                description=f"```\n[ {reels[0]} ][ {reels[1]} ][ {reels[2]} ]\n```",
                color=discord.Color.red()
            )
            embed.add_field(name="💰 Bet", value=f"{bet} points", inline=True)
            embed.add_field(name="💸 Lost", value=f"-{bet} points", inline=True)
            embed.add_field(name="💳 Balance", value=f"{user_data['points'] - bet} points", inline=True)
            
            if reels[0] == reels[1] or reels[1] == reels[2]:
                embed.set_footer(text="So close! Two matching symbols!")
                
            await self.db.statistics.update_one(
                {"_id": "global_stats"},
                {
                    "$inc": {
                        "game_stats.slots_played": 1
                    }
                }
            )
                
        for item in view.children:
            item.disabled = True
            
        await message.edit(embed=embed, view=view)
        
    @slots.command(name="stats", description="View your slot machine statistics")
    async def slots_stats(self, ctx):
        user_data = await self.get_user_data(ctx.author.id)
        stats = user_data.get("statistics", {})
        game_stats = user_data.get("game_stats", {}).get("slots", {})
        
        # Combine statistics from both sources
        played = stats.get("slots_played", 0) or game_stats.get("played", 0)
        won = stats.get("slots_won", 0) or game_stats.get("won", 0)
        lost = played - won
        profit = stats.get("slots_profit", 0) or game_stats.get("profit", 0)
        
        embed = discord.Embed(
            title="🎰 Your Slots Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="🎮 Games Played", value=str(played), inline=True)
        embed.add_field(name="🏆 Games Won", value=str(won), inline=True)
        embed.add_field(name="💔 Games Lost", value=str(lost), inline=True)
        
        if played > 0:
            win_rate = (won / played) * 100
            embed.add_field(name="📊 Win Rate", value=f"{win_rate:.1f}%", inline=True)
        
        embed.add_field(name="💰 Net Profit/Loss", value=f"{profit:+d} points", inline=True)
        embed.add_field(name="🎯 Biggest Win", value=f"{stats.get('slots_biggest_win', 0)} points", inline=True)
        embed.add_field(name="🔥 Current Streak", value=str(stats.get("slots_current_streak", 0)), inline=True)
        embed.add_field(name="⭐ Best Streak", value=str(stats.get("slots_best_streak", 0)), inline=True)
        embed.add_field(name="💵 Current Balance", value=f"{user_data['points']} points", inline=True)
        
        await ctx.send(embed=embed, ephemeral=True)
    
    @slots.command(name="odds", description="View slot machine odds")
    async def slots_odds(self, ctx):
        embed = discord.Embed(
            title="🎰 Slot Machine Odds",
            description="Match 3 symbols to win!",
            color=discord.Color.gold()
        )
        
        for symbol, data in sorted(self.symbols.items(), key=lambda x: x[1]["payout"], reverse=True):
            embed.add_field(
                name=f"{symbol} {data['name']}",
                value=f"Win: **{data['payout']}x** bet\nChance: **{data['weight']}%**",
                inline=True
            )
            
        embed.add_field(
            name="💔 No Match",
            value=f"Lose bet\nChance: **{self.lose_weight:.1f}%**",
            inline=True
        )
        
        embed.add_field(
            name="📊 Game Info",
            value=f"• Min bet: 5 points\n• Max bet: 200 points\n• House Edge: ~0%\n• Pure luck based",
            inline=False
        )
        
        embed.set_footer(text="Good luck! 🍀")
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SlotsCog(bot))