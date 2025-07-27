import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone
import random
import asyncio
from typing import Optional, List, Dict
import traceback

class GamblingView(discord.ui.View):
    def __init__(self, host_id: int, bet_amount: int, max_players: int = 10):
        super().__init__(timeout=60)
        self.host_id = host_id
        self.players = {host_id: bet_amount}
        self.max_players = max_players
        self.started = False
        
    @discord.ui.button(label="🎲 Join Gamble", style=discord.ButtonStyle.primary)
    async def join_gamble(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.started:
            await interaction.response.send_message("❌ Gamble already started!", ephemeral=True)
            return
            
        if interaction.user.id in self.players:
            await interaction.response.send_message("✅ You're already in!", ephemeral=True)
            return
            
        if len(self.players) >= self.max_players:
            await interaction.response.send_message("❌ Gamble is full!", ephemeral=True)
            return
        
        modal = BetModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🚀 Start Game", style=discord.ButtonStyle.success)
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Only the host can start!", ephemeral=True)
            return
            
        if len(self.players) < 2:
            await interaction.response.send_message("❌ Need at least 2 players!", ephemeral=True)
            return
            
        self.started = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

class BetModal(discord.ui.Modal):
    def __init__(self, view: GamblingView):
        super().__init__(title="Place Your Bet")
        self.view = view
        
        self.bet = discord.ui.TextInput(
            label="Bet Amount",
            placeholder="Enter points to bet (min 10)",
            min_length=1,
            max_length=6
        )
        self.add_item(self.bet)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.bet.value)
            if bet_amount < 10:
                await interaction.response.send_message("❌ Minimum bet is 10 points!", ephemeral=True)
                return
                
            user_data = await interaction.client.get_cog("EventsCog").db.users.find_one({"user_id": interaction.user.id})
            if not user_data or user_data.get("points", 0) < bet_amount:
                await interaction.response.send_message("❌ Insufficient points!", ephemeral=True)
                return
            
            await interaction.client.get_cog("EventsCog").db.users.update_one(
                {"user_id": interaction.user.id},
                {"$inc": {"points": -bet_amount}}
            )
            
            self.view.players[interaction.user.id] = bet_amount
            
            embed = interaction.message.embeds[0]
            total_pot = sum(self.view.players.values())
            embed.set_field_at(0, name="💰 Total Pot", value=f"**{total_pot}** points", inline=True)
            embed.set_field_at(1, name="👥 Players", value=f"**{len(self.view.players)}**/{self.view.max_players}", inline=True)
            
            player_list = []
            for uid, bet in self.view.players.items():
                user = interaction.client.get_user(uid)
                player_list.append(f"{user.mention if user else 'Unknown'}: **{bet}** points")
            embed.set_field_at(2, name="🎲 Current Bets", value="\n".join(player_list[:5]), inline=False)
            
            await interaction.response.edit_message(embed=embed, view=self.view)
            
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount!", ephemeral=True)

class ReactEventView(discord.ui.View):
    def __init__(self, prize: int, max_winners: int, event_type: str):
        super().__init__(timeout=30)
        self.prize = prize
        self.max_winners = max_winners
        self.event_type = event_type
        self.participants = []
        self.winners = []
        
    @discord.ui.button(label="🎯 React!", style=discord.ButtonStyle.success, emoji="🍪")
    async def react_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            await interaction.response.send_message("✅ You already reacted!", ephemeral=True)
            return
            
        self.participants.append(interaction.user.id)
        await interaction.response.send_message("✅ Reaction recorded!", ephemeral=True)

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.active_gambles = {}
        
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)

    @commands.hybrid_command(name="gamble", description="Start a gambling game (solo or group)")
    @app_commands.describe(
        bet="Your bet amount (min 10 points)",
        mode="solo or group",
        win_percentage="Winner percentage (10-90, default 50)"
    )
    async def gamble(self, ctx, bet: int, mode: str = "solo", win_percentage: int = 50):
        try:
            if bet < 10:
                await ctx.send("❌ Minimum bet is 10 points!", ephemeral=True)
                return
                
            if mode not in ["solo", "group"]:
                await ctx.send("❌ Mode must be 'solo' or 'group'!", ephemeral=True)
                return
                
            if win_percentage < 10 or win_percentage > 90:
                await ctx.send("❌ Win percentage must be between 10-90!", ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            if not user_data or user_data.get("points", 0) < bet:
                await ctx.send("❌ Insufficient points!", ephemeral=True)
                return
            
            if mode == "solo":
                await self.db.users.update_one(
                    {"user_id": ctx.author.id},
                    {"$inc": {"points": -bet}}
                )
                
                roll = random.randint(1, 100)
                won = roll <= win_percentage
                
                if won:
                    winnings = int(bet * (100 / win_percentage))
                    await self.db.users.update_one(
                        {"user_id": ctx.author.id},
                        {"$inc": {"points": winnings}}
                    )
                    
                    embed = discord.Embed(
                        title="🎰 Solo Gamble - YOU WON!",
                        description=f"Roll: **{roll}** (needed ≤{win_percentage})",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="💰 Bet", value=f"{bet} points", inline=True)
                    embed.add_field(name="🏆 Won", value=f"**{winnings}** points", inline=True)
                    embed.add_field(name="📈 Profit", value=f"+{winnings - bet} points", inline=True)
                else:
                    embed = discord.Embed(
                        title="🎰 Solo Gamble - You Lost",
                        description=f"Roll: **{roll}** (needed ≤{win_percentage})",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="💸 Lost", value=f"{bet} points", inline=True)
                    embed.add_field(name="🎲 Odds", value=f"{win_percentage}%", inline=True)
                
                await ctx.send(embed=embed)
                
            else:
                await self.db.users.update_one(
                    {"user_id": ctx.author.id},
                    {"$inc": {"points": -bet}}
                )
                
                embed = discord.Embed(
                    title="🎲 Group Gamble Started!",
                    description=f"Join the gamble! Winner takes all!\nWin Rate: **{win_percentage}%**",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="💰 Total Pot", value=f"**{bet}** points", inline=True)
                embed.add_field(name="👥 Players", value="**1**/10", inline=True)
                embed.add_field(name="🎲 Current Bets", value=f"{ctx.author.mention}: **{bet}** points", inline=False)
                embed.set_footer(text="60 seconds to join!")
                
                view = GamblingView(ctx.author.id, bet)
                message = await ctx.send(embed=embed, view=view)
                
                await view.wait()
                
                if not view.started or len(view.players) < 2:
                    for uid, amount in view.players.items():
                        await self.db.users.update_one(
                            {"user_id": uid},
                            {"$inc": {"points": amount}}
                        )
                    
                    embed = discord.Embed(
                        title="❌ Gamble Cancelled",
                        description="Not enough players or not started. Points refunded!",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed, view=None)
                    return
                
                total_pot = sum(view.players.values())
                players = list(view.players.keys())
                
                roll = random.randint(1, 100)
                if roll <= win_percentage:
                    winner_id = random.choice(players)
                    winner = self.bot.get_user(winner_id)
                    
                    await self.db.users.update_one(
                        {"user_id": winner_id},
                        {"$inc": {"points": total_pot}}
                    )
                    
                    embed = discord.Embed(
                        title="🎰 Group Gamble - WINNER!",
                        description=f"{winner.mention if winner else 'Unknown'} wins the pot!",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="🎲 Roll", value=f"**{roll}** (needed ≤{win_percentage})", inline=True)
                    embed.add_field(name="💰 Prize", value=f"**{total_pot}** points", inline=True)
                    embed.add_field(name="👥 Players", value=len(players), inline=True)
                else:
                    embed = discord.Embed(
                        title="🎰 Group Gamble - House Wins!",
                        description="No winner this time! All bets lost.",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="🎲 Roll", value=f"**{roll}** (needed ≤{win_percentage})", inline=True)
                    embed.add_field(name="💸 Lost", value=f"**{total_pot}** points", inline=True)
                
                await message.edit(embed=embed, view=None)
                
            await self.log_action(
                ctx.guild.id,
                f"🎰 {ctx.author.mention} {'won' if mode == 'solo' and won else 'started'} a {mode} gamble",
                discord.Color.gold()
            )
            
        except Exception as e:
            print(f"Error in gamble: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="luckydraw", description="Start a lucky draw (Owner only)")
    @app_commands.describe(
        prize="Prize amount in points",
        winners="Number of winners",
        duration="Duration in seconds"
    )
    async def luckydraw(self, ctx, prize: int, winners: int = 1, duration: int = 30):
        try:
            if not await self.is_owner(ctx.author.id):
                await ctx.send("❌ Owner only command!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🎉 LUCKY DRAW!",
                description=f"React with 🎟️ to enter!\n**Prize:** {prize} points each",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="🏆 Winners", value=f"**{winners}**", inline=True)
            embed.add_field(name="⏰ Duration", value=f"**{duration}** seconds", inline=True)
            embed.add_field(name="💰 Total Prize", value=f"**{prize * winners}** points", inline=True)
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("🎟️")
            
            await asyncio.sleep(duration)
            
            message = await ctx.channel.fetch_message(message.id)
            reaction = None
            for r in message.reactions:
                if str(r.emoji) == "🎟️":
                    reaction = r
                    break
            
            if not reaction or reaction.count <= 1:
                embed = discord.Embed(
                    title="❌ Lucky Draw Cancelled",
                    description="No participants!",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                return
            
            participants = []
            async for user in reaction.users():
                if not user.bot:
                    participants.append(user)
            
            if len(participants) < winners:
                winners = len(participants)
            
            selected_winners = random.sample(participants, winners)
            
            for winner in selected_winners:
                await self.db.users.update_one(
                    {"user_id": winner.id},
                    {"$inc": {"points": prize}},
                    upsert=True
                )
            
            winner_mentions = [w.mention for w in selected_winners]
            
            embed = discord.Embed(
                title="🎉 Lucky Draw Results!",
                description=f"**Winners:**\n" + "\n".join(winner_mentions),
                color=discord.Color.green()
            )
            embed.add_field(name="💰 Prize Each", value=f"**{prize}** points", inline=True)
            embed.add_field(name="👥 Participants", value=len(participants), inline=True)
            
            await message.edit(embed=embed)
            await message.reply(f"Congratulations {', '.join(winner_mentions)}! 🎉")
            
        except Exception as e:
            print(f"Error in luckydraw: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="reactevent", description="Start a reaction event (Owner only)")
    @app_commands.describe(
        prize="Prize per winner",
        winners="Number of winners",
        duration="Duration in seconds",
        mode="random or first"
    )
    async def reactevent(self, ctx, prize: int, winners: int = 1, duration: int = 20, mode: str = "random"):
        try:
            if not await self.is_owner(ctx.author.id):
                await ctx.send("❌ Owner only command!", ephemeral=True)
                return
            
            if mode not in ["random", "first"]:
                await ctx.send("❌ Mode must be 'random' or 'first'!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="⚡ REACTION EVENT!",
                description=f"Click the button to participate!\n**Mode:** {mode.title()}",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="💰 Prize", value=f"**{prize}** points each", inline=True)
            embed.add_field(name="🏆 Winners", value=f"**{winners}**", inline=True)
            embed.add_field(name="⏰ Time", value=f"**{duration}** seconds", inline=True)
            
            view = ReactEventView(prize, winners, mode)
            message = await ctx.send(embed=embed, view=view)
            
            await asyncio.sleep(duration)
            
            for item in view.children:
                item.disabled = True
            await message.edit(view=view)
            
            if not view.participants:
                embed = discord.Embed(
                    title="❌ No Participants",
                    description="Nobody participated!",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed, view=None)
                return
            
            if mode == "first":
                selected_winners = view.participants[:winners]
            else:
                if len(view.participants) <= winners:
                    selected_winners = view.participants
                else:
                    selected_winners = random.sample(view.participants, winners)
            
            for winner_id in selected_winners:
                await self.db.users.update_one(
                    {"user_id": winner_id},
                    {"$inc": {"points": prize}},
                    upsert=True
                )
            
            winner_mentions = [f"<@{uid}>" for uid in selected_winners]
            
            embed = discord.Embed(
                title="⚡ Reaction Event Results!",
                description=f"**Winners:**\n" + "\n".join(winner_mentions),
                color=discord.Color.green()
            )
            embed.add_field(name="💰 Prize", value=f"**{prize}** points each", inline=True)
            embed.add_field(name="👥 Total Reactions", value=len(view.participants), inline=True)
            embed.add_field(name="🎯 Mode", value=mode.title(), inline=True)
            
            await message.edit(embed=embed, view=None)
            
        except Exception as e:
            print(f"Error in reactevent: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="fountain", description="Point fountain - distribute points to random users (Owner only)")
    @app_commands.describe(
        total="Total points to distribute",
        users="Number of users to receive points"
    )
    async def fountain(self, ctx, total: int, users: int):
        try:
            if not await self.is_owner(ctx.author.id):
                await ctx.send("❌ Owner only command!", ephemeral=True)
                return
            
            online_members = [m for m in ctx.guild.members if not m.bot and m.status != discord.Status.offline]
            
            if len(online_members) < users:
                users = len(online_members)
            
            if users == 0:
                await ctx.send("❌ No online users!", ephemeral=True)
                return
            
            selected_users = random.sample(online_members, users)
            points_each = total // users
            
            embed = discord.Embed(
                title="⛲ Point Fountain Activated!",
                description=f"Distributing **{total}** points to **{users}** lucky users!",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            winner_list = []
            for user in selected_users:
                await self.db.users.update_one(
                    {"user_id": user.id},
                    {"$inc": {"points": points_each}},
                    upsert=True
                )
                winner_list.append(f"{user.mention}: +**{points_each}** points")
            
            embed.add_field(
                name="💰 Lucky Recipients",
                value="\n".join(winner_list[:10]) + (f"\n...and {len(winner_list)-10} more" if len(winner_list) > 10 else ""),
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"⛲ {ctx.author.mention} activated point fountain: {total} points to {users} users",
                discord.Color.blue()
            )
            
        except Exception as e:
            print(f"Error in fountain: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="bless", description="Randomly bless online users with points (Owner only)")
    @app_commands.describe(
        amount="Points to give each blessed user",
        count="Number of users to bless (0 for random)"
    )
    async def bless(self, ctx, amount: int, count: int = 0):
        try:
            if not await self.is_owner(ctx.author.id):
                await ctx.send("❌ Owner only command!", ephemeral=True)
                return
            
            online_members = [m for m in ctx.guild.members if not m.bot and m.status != discord.Status.offline]
            
            if not online_members:
                await ctx.send("❌ No online users!", ephemeral=True)
                return
            
            if count == 0:
                count = random.randint(1, min(10, len(online_members)))
            else:
                count = min(count, len(online_members))
            
            blessed_users = random.sample(online_members, count)
            
            embed = discord.Embed(
                title="✨ Random Blessing!",
                description=f"The gods have blessed {count} users with **{amount}** points each!",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            
            blessed_list = []
            for user in blessed_users:
                await self.db.users.update_one(
                    {"user_id": user.id},
                    {"$inc": {"points": amount}},
                    upsert=True
                )
                blessed_list.append(user.mention)
                
                try:
                    dm_embed = discord.Embed(
                        title="✨ You've Been Blessed!",
                        description=f"You received **{amount}** points from a random blessing in **{ctx.guild.name}**!",
                        color=discord.Color.gold()
                    )
                    await user.send(embed=dm_embed)
                except:
                    pass
            
            embed.add_field(
                name="🌟 Blessed Users",
                value="\n".join(blessed_list),
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error in bless: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="lottery", description="Buy lottery tickets")
    @app_commands.describe(
        tickets="Number of tickets to buy (max 10)"
    )
    async def lottery(self, ctx, tickets: int = 1):
        try:
            if tickets < 1 or tickets > 10:
                await ctx.send("❌ You can buy 1-10 tickets!", ephemeral=True)
                return
            
            lottery_config = await self.db.lottery.find_one({"active": True})
            if not lottery_config:
                await ctx.send("❌ No active lottery!", ephemeral=True)
                return
            
            ticket_price = lottery_config.get("ticket_price", 50)
            total_cost = ticket_price * tickets
            
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            if not user_data or user_data.get("points", 0) < total_cost:
                await ctx.send(f"❌ You need **{total_cost}** points for {tickets} tickets!", ephemeral=True)
                return
            
            user_tickets = lottery_config.get("participants", {}).get(str(ctx.author.id), 0)
            if user_tickets + tickets > 10:
                await ctx.send(f"❌ You can only have up to 10 tickets! You have {user_tickets}.", ephemeral=True)
                return
            
            await self.db.users.update_one(
                {"user_id": ctx.author.id},
                {"$inc": {"points": -total_cost}}
            )
            
            await self.db.lottery.update_one(
                {"active": True},
                {
                    "$inc": {
                        f"participants.{ctx.author.id}": tickets,
                        "total_tickets": tickets,
                        "prize_pool": total_cost
                    }
                }
            )
            
            embed = discord.Embed(
                title="🎟️ Lottery Tickets Purchased!",
                description=f"You bought **{tickets}** tickets for **{total_cost}** points!",
                color=discord.Color.green()
            )
            embed.add_field(name="Your Tickets", value=f"**{user_tickets + tickets}**/10", inline=True)
            embed.add_field(name="Draw Time", value=f"<t:{int(lottery_config['draw_time'].timestamp())}:R>", inline=True)
            embed.add_field(name="Current Pool", value=f"**{lottery_config['prize_pool'] + total_cost}** points", inline=True)
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in lottery: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    @commands.hybrid_command(name="startlottery", description="Start a new lottery (Owner only)")
    @app_commands.describe(
        ticket_price="Price per ticket",
        base_prize="Base prize pool",
        duration_hours="Hours until draw"
    )
    async def startlottery(self, ctx, ticket_price: int = 50, base_prize: int = 1000, duration_hours: int = 24):
        try:
            if not await self.is_owner(ctx.author.id):
                await ctx.send("❌ Owner only command!", ephemeral=True)
                return
            
            active = await self.db.lottery.find_one({"active": True})
            if active:
                await ctx.send("❌ Lottery already active!", ephemeral=True)
                return
            
            draw_time = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
            
            lottery_data = {
                "active": True,
                "ticket_price": ticket_price,
                "prize_pool": base_prize,
                "base_prize": base_prize,
                "participants": {},
                "total_tickets": 0,
                "start_time": datetime.now(timezone.utc),
                "draw_time": draw_time,
                "channel_id": ctx.channel.id,
                "guild_id": ctx.guild.id
            }
            
            await self.db.lottery.insert_one(lottery_data)
            
            embed = discord.Embed(
                title="🎰 LOTTERY STARTED!",
                description=f"Buy tickets with `/lottery`!",
                color=discord.Color.gold(),
                timestamp=draw_time
            )
            embed.add_field(name="🎟️ Ticket Price", value=f"**{ticket_price}** points", inline=True)
            embed.add_field(name="💰 Starting Pool", value=f"**{base_prize}** points", inline=True)
            embed.add_field(name="⏰ Draw Time", value=f"<t:{int(draw_time.timestamp())}:F>", inline=True)
            embed.add_field(name="📋 Rules", value="• Max 10 tickets per person\n• Winner takes entire pool\n• More tickets = higher chance", inline=False)
            embed.set_footer(text="Good luck! 🍀")
            
            await ctx.send(embed=embed)
            
            await asyncio.sleep(duration_hours * 3600)
            await self.draw_lottery()
            
        except Exception as e:
            print(f"Error in startlottery: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

    async def draw_lottery(self):
        try:
            lottery = await self.db.lottery.find_one({"active": True})
            if not lottery:
                return
            
            participants = lottery.get("participants", {})
            if not participants:
                await self.db.lottery.update_one(
                    {"active": True},
                    {"$set": {"active": False}}
                )
                return
            
            ticket_pool = []
            for user_id, tickets in participants.items():
                ticket_pool.extend([user_id] * tickets)
            
            winner_id = random.choice(ticket_pool)
            winner = self.bot.get_user(int(winner_id))
            
            prize_pool = lottery["prize_pool"]
            
            await self.db.users.update_one(
                {"user_id": int(winner_id)},
                {"$inc": {"points": prize_pool}}
            )
            
            await self.db.lottery.update_one(
                {"active": True},
                {"$set": {"active": False, "winner": winner_id}}
            )
            
            channel = self.bot.get_channel(lottery["channel_id"])
            if channel:
                embed = discord.Embed(
                    title="🎰 LOTTERY WINNER!",
                    description=f"{winner.mention if winner else 'Unknown'} wins **{prize_pool}** points!",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="🎟️ Winning Tickets", value=f"**{participants[winner_id]}**/{lottery['total_tickets']}", inline=True)
                embed.add_field(name="👥 Participants", value=len(participants), inline=True)
                embed.add_field(name="💰 Prize Pool", value=f"**{prize_pool}** points", inline=True)
                
                await channel.send(embed=embed)
                
                if winner:
                    try:
                        dm_embed = discord.Embed(
                            title="🎉 YOU WON THE LOTTERY!",
                            description=f"Congratulations! You won **{prize_pool}** points!",
                            color=discord.Color.gold()
                        )
                        await winner.send(embed=dm_embed)
                    except:
                        pass
                        
        except Exception as e:
            print(f"Error drawing lottery: {e}")

async def setup(bot):
    await bot.add_cog(EventsCog(bot))