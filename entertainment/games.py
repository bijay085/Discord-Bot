import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from typing import Optional

class GamesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.current_page = "main"
        
    @discord.ui.select(
        placeholder="Select a game to learn more...",
        options=[
            discord.SelectOption(label="🎲 Bet System", value="bet", description="Group betting game with number guessing"),
            discord.SelectOption(label="🎭 Rob System", value="rob", description="Steal points from other users"),
            discord.SelectOption(label="🎁 Points Giveaway", value="giveaway", description="Owner-hosted point giveaways"),
            discord.SelectOption(label="🎰 Divine Gamble", value="gamble", description="High-risk blessing/curse system"),
            discord.SelectOption(label="🎰 Slot Machine", value="slots", description="Classic 3-reel slot machine"),
            discord.SelectOption(label="🏠 Return to Main", value="main", description="Go back to overview")
        ]
    )
    async def select_game(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.current_page = select.values[0]
        embed = self.get_embed_for_page(self.current_page)
        
        # Update select menu placeholder
        select.placeholder = "Currently viewing: " + select.values[0].title()
        
        await interaction.response.edit_message(embed=embed, view=self)
        
    def get_embed_for_page(self, page: str) -> discord.Embed:
        if page == "main":
            return self.get_main_embed()
        elif page == "bet":
            return self.get_bet_embed()
        elif page == "rob":
            return self.get_rob_embed()
        elif page == "giveaway":
            return self.get_giveaway_embed()
        elif page == "gamble":
            return self.get_gamble_embed()
        elif page == "slots":
            return self.get_slots_embed()
        else:
            return self.get_main_embed()
            
    def get_main_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎮 Cookie Bot Games & Entertainment",
            description="Welcome to the entertainment system! We have various games to earn or lose points. Choose wisely!",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="🎲 Available Games",
            value=(
                "• **Bet** - Group betting with number guessing\n"
                "• **Rob** - Steal points based on trust scores\n"
                "• **Giveaway** - Join point giveaways\n"
                "• **Divine Gamble** - Ultimate risk for blessing\n"
                "• **Slots** - Classic slot machine"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Higher trust score = better rob success\n"
                "• All games use your points balance\n"
                "• Some games have cooldowns\n"
                "• Gambling can be addictive!"
            ),
            inline=False
        )
        
        embed.set_footer(text="Select a game from the dropdown to learn more!")
        return embed
        
    def get_bet_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎲 Bet System Guide",
            description="A multiplayer betting game where players guess numbers!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 How to Play",
            value=(
                "`/bet solo points <amount>` - Solo vs bot\n"
                "`/bet group points` - Multiplayer betting"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Game Rules",
            value=(
                "• Guess a number between 1-10 (solo) or 1-X (group)\n"
                "• Closest to winning number wins all bets\n"
                "• Exact match = 50% profit bonus\n"
                "• Group range increases with more players"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💰 Rewards",
            value=(
                "**Solo Mode:**\n"
                "• Exact match: Bet × 1.5\n"
                "• Close guess (±2): 15% back\n"
                "• Wrong: Lose bet\n\n"
                "**Group Mode:**\n"
                "• Winner takes entire pot\n"
                "• Closest guess gets 50% back"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⏱️ Timers",
            value=(
                "• Join phase: 60 seconds\n"
                "• Guess phase: 30 seconds\n"
                "• Host can manage timer"
            ),
            inline=False
        )
        
        return embed
        
    def get_rob_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎭 Rob System Guide",
            description="Steal points from others based on trust scores!",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="📋 Commands",
            value=(
                "`/rob @user` - Attempt to rob someone\n"
                "`/robstats` - Check your rob statistics\n"
                "`/robhelp` - View detailed help"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Success Rates",
            value=(
                "**Your trust > Their trust:**\n"
                "• Victim <20: 90% success\n"
                "• Victim 20-40: 70% success\n"
                "• Victim 40-60: 50% success\n"
                "• Victim 60+: 30% success\n\n"
                "**Your trust < Their trust:** 20% fixed"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💰 Risk & Reward",
            value=(
                "**Success:** Steal 20-30% of their points\n"
                "**Failure:** Pay 30% penalty to victim\n"
                "**Trust Changes:** +0.5 on win, -1 on loss"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⏰ Cooldowns",
            value=(
                "• Max 2 rob attempts per 24h\n"
                "• 3 hour cooldown between attempts\n"
                "• Can be robbed max 2 times per 24h\n"
                "• Same person once per day only"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Special Rules",
            value=(
                "• Target's stats hidden until after attempt\n"
                "• Robbing 0 points wastes your attempt\n"
                "• Victims with <3 points give all they have\n"
                "• No minimum requirements to rob"
            ),
            inline=False
        )
        
        return embed
        
    def get_giveaway_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎁 Points Giveaway Guide",
            description="Free points giveaways hosted by the bot owner!",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="📋 Commands",
            value=(
                "`/pgiveaway start <points> <time>` - Start giveaway (Owner only)\n"
                "`/pgiveaway end` - End early (Owner only)\n"
                "`/pgiveaway list` - View active giveaways"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 How to Enter",
            value=(
                "• React with 🎉 to enter\n"
                "• One entry per person\n"
                "• Remove reaction to leave\n"
                "• Must not be blacklisted"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💰 Prizes",
            value=(
                "• Points come from system (free!)\n"
                "• Winner gets full amount\n"
                "• Winner notified via DM\n"
                "• Public announcement in channel"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⏰ Duration",
            value=(
                "• Set by owner (5m, 1h, 1d, etc)\n"
                "• Can be ended early\n"
                "• Auto-picks winner at end\n"
                "• Live entry counter"
            ),
            inline=False
        )
        
        return embed
        
    def get_gamble_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎰 Divine Gamble Guide",
            description="The ultimate high-risk blessing/curse system!",
            color=discord.Color.dark_purple()
        )
        
        embed.add_field(
            name="📋 Commands",
            value=(
                "`/gamble divine` - Take the gamble\n"
                "`/gamble stats` - Your gambling history\n"
                "`/gamble requirements` - Check requirements"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Requirements",
            value=(
                "• **Invites:** 5+ verified (still in server)\n"
                "• **Trust:** 60+ (costs 15 to enter)\n"
                "• **Points:** 20+ (costs 10 to enter)\n"
                "• **Cooldown:** 7 days"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💀 Cursed (95% chance)",
            value=(
                "• Lose 15 trust permanently\n"
                "• Lose 10 points permanently\n"
                "• Get 'Cursed Gambler' role (24h)\n"
                "• Wait 7 days to try again"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🌟 Blessed (5% chance)",
            value=(
                "• Get 45 trust back (+30 profit)\n"
                "• Get 130 points back (+120 profit)\n"
                "• 'Divine Chosen' role (exclusive)\n"
                "• Only ONE blessed per server!"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Warning",
            value=(
                "• Entry costs are NON-REFUNDABLE\n"
                "• This is designed to make you lose\n"
                "• 95% chance of losing everything\n"
                "• Only gamble what you can afford to lose!"
            ),
            inline=False
        )
        
        return embed
        
    def get_slots_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎰 Slot Machine Guide",
            description="Classic 3-reel slot machine with pure luck!",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="📋 Commands",
            value=(
                "`/slots play <amount>` - Spin the slots\n"
                "`/slots stats` - View your statistics\n"
                "`/slots odds` - Check winning odds"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 How to Win",
            value=(
                "• Match 3 symbols in a row\n"
                "• No partial matches count\n"
                "• Pure luck - no skill involved\n"
                "• Each spin is independent"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💰 Payouts & Odds",
            value=(
                "🍒 **Cherry** - 1.5x (20% chance)\n"
                "🍋 **Lemon** - 2x (10% chance)\n"
                "🍊 **Orange** - 3x (5% chance)\n"
                "🍇 **Grapes** - 5x (3% chance)\n"
                "💎 **Diamond** - 10x (1% chance)\n"
                "7️⃣ **Seven** - 50x (0.2% chance)\n"
                "💔 **No match** - Lose (60.8% chance)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Limits",
            value=(
                "• Min bet: 5 points\n"
                "• Max bet: 200 points\n"
                "• Can't bet >25% of balance\n"
                "• 10 second cooldown between spins"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 Statistics",
            value=(
                "• Track wins/losses\n"
                "• See your profit/loss\n"
                "• Win streaks recorded\n"
                "• Biggest win saved"
            ),
            inline=False
        )
        
        return embed

class GamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.hybrid_command(name="games", description="View all available games and how to play")
    async def games(self, ctx):
        view = GamesView()
        embed = view.get_main_embed()
        await ctx.send(embed=embed, view=view)
        
    @commands.hybrid_command(name="entertainment", description="View all entertainment features")
    async def entertainment(self, ctx):
        embed = discord.Embed(
            title="🎪 Cookie Bot Entertainment System",
            description="All the ways to have fun and gamble your points!",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        games_list = [
            ("🎲 **Betting**", "Solo or group number guessing", "`/bet`"),
            ("🎭 **Robbing**", "Steal from others using trust", "`/rob`"),
            ("🎁 **Giveaways**", "Free points from owner", "`/pgiveaway`"),
            ("🎰 **Divine Gamble**", "5% chance for massive rewards", "`/gamble divine`"),
            ("🎰 **Slots**", "Classic slot machine", "`/slots play`")
        ]
        
        for name, desc, cmd in games_list:
            embed.add_field(
                name=name,
                value=f"{desc}\n{cmd}",
                inline=True
            )
            
        embed.add_field(
            name="📚 Learn More",
            value="Use `/games` for detailed guides on each game!",
            inline=False
        )
        
        embed.set_footer(text="Remember: The house always wins! Gamble responsibly.")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GamesCog(bot))