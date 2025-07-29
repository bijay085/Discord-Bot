import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

class GiveawayView(discord.ui.View):
    def __init__(self, cog, giveaway_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id
        
    @discord.ui.button(label="End Early", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def end_early(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        if interaction.user.id != giveaway["host_id"]:
            await interaction.response.send_message("❌ Only the host can end the giveaway!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.cog.end_giveaway(self.giveaway_id, manual=True)
        
    @discord.ui.button(label="Participants", style=discord.ButtonStyle.secondary, emoji="👥")
    async def show_participants(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        entries = giveaway.get("entries", [])
        if not entries:
            await interaction.response.send_message("📭 No participants yet!", ephemeral=True)
            return
            
        participant_list = []
        for i, user_id in enumerate(entries[:20], 1):
            user = self.cog.bot.get_user(user_id)
            if user:
                participant_list.append(f"{i}. {user.mention}")
                
        embed = discord.Embed(
            title="👥 Giveaway Participants",
            description="\n".join(participant_list) + (f"\n\n*And {len(entries) - 20} more...*" if len(entries) > 20 else ""),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Total: {len(entries)} participants")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.active_giveaways = {}
        self.check_giveaways.start()
        
    async def cog_load(self):
        print("🎮 GiveawayCog loaded")
        
    async def cog_unload(self):
        self.check_giveaways.cancel()
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
            
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
        
    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        now = datetime.now(timezone.utc)
        to_end = []
        
        for giveaway_id, giveaway in self.active_giveaways.items():
            if giveaway["end_time"] and now >= giveaway["end_time"]:
                to_end.append(giveaway_id)
                
        for giveaway_id in to_end:
            await self.end_giveaway(giveaway_id)
            
    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()
        
    async def end_giveaway(self, giveaway_id: str, manual: bool = False):
        giveaway = self.active_giveaways.get(giveaway_id)
        if not giveaway:
            return
            
        channel = self.bot.get_channel(giveaway["channel_id"])
        if not channel:
            del self.active_giveaways[giveaway_id]
            return
            
        try:
            message = await channel.fetch_message(giveaway["message_id"])
        except:
            del self.active_giveaways[giveaway_id]
            return
            
        # Get final participant list
        reaction = None
        for r in message.reactions:
            if str(r.emoji) == giveaway["emoji"]:
                reaction = r
                break
                
        if not reaction:
            entries = []
        else:
            entries = []
            async for user in reaction.users():
                if not user.bot and user.id != giveaway["host_id"]:
                    # Check if user is eligible
                    user_data = await self.db.users.find_one({"user_id": user.id})
                    if not user_data or user_data.get("blacklisted"):
                        continue
                    entries.append(user.id)
        
        # Pick winner
        if entries:
            winner_id = random.choice(entries)
            winner = self.bot.get_user(winner_id)
            
            if winner:
                # Award points
                await self.db.users.update_one(
                    {"user_id": winner_id},
                    {
                        "$inc": {"points": giveaway["prize"]},
                        "$set": {"last_active": datetime.now(timezone.utc)}
                    },
                    upsert=True
                )
                
                # Update embed
                embed = discord.Embed(
                    title="🎉 GIVEAWAY ENDED!",
                    description=f"**Winner:** {winner.mention}\n**Prize:** {giveaway['prize']} points",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="👥 Total Entries", value=str(len(entries)), inline=True)
                embed.add_field(name="🎁 Prize Claimed", value="✅", inline=True)
                embed.set_footer(text=f"Hosted by {self.bot.get_user(giveaway['host_id'])}")
                
                # Disable view
                for item in message.components:
                    for child in item.children:
                        child.disabled = True
                
                await message.edit(embed=embed, view=None)
                
                # Send winner announcement
                winner_announce = discord.Embed(
                    title="🎊 CONGRATULATIONS!",
                    description=f"{winner.mention} won **{giveaway['prize']}** points!",
                    color=discord.Color.gold()
                )
                await channel.send(embed=winner_announce)
                
                # DM winner
                try:
                    winner_dm = discord.Embed(
                        title="🎉 You Won a Giveaway!",
                        description=f"You won **{giveaway['prize']}** points in {channel.guild.name}!",
                        color=discord.Color.gold(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    winner_dm.add_field(name="💰 Points Added", value=f"+{giveaway['prize']}", inline=True)
                    await winner.send(embed=winner_dm)
                except:
                    pass
                
                # Log
                await self.log_action(
                    channel.guild.id,
                    f"🎁 {winner.mention} won **{giveaway['prize']}** points in giveaway!",
                    discord.Color.gold()
                )
            else:
                # Winner not found
                embed = discord.Embed(
                    title="🎁 GIVEAWAY ENDED",
                    description="Winner could not be determined!",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed, view=None)
        else:
            # No entries
            embed = discord.Embed(
                title="😢 GIVEAWAY ENDED",
                description="No valid entries!",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text="No one participated")
            
            await message.edit(embed=embed, view=None)
            
            await channel.send("💔 No one entered the giveaway.")
        
        # Remove from active
        del self.active_giveaways[giveaway_id]
    
    @commands.hybrid_group(name="pgiveaway", description="Points giveaway system")
    async def pgiveaway(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/pgiveaway start` to create a giveaway!", ephemeral=True)
    
    @pgiveaway.command(name="start", description="Start a points giveaway (Owner only)")
    @app_commands.describe(
        points="Amount of points to give away",
        duration="Duration (e.g., 5m, 1h, 1d)"
    )
    async def pgiveaway_start(self, ctx, points: int, duration: Optional[str] = "5m"):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ Only the bot owner can create giveaways!", ephemeral=True)
            return
            
        if points <= 0:
            await ctx.send("❌ Points must be positive!", ephemeral=True)
            return
            
        # Use default emoji
        emoji = "🎉"
        
        # Parse duration
        end_time = None
        if duration:
            multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
            unit = duration[-1].lower()
            if unit in multipliers and duration[:-1].isdigit():
                seconds = int(duration[:-1]) * multipliers[unit]
                if seconds > 0:
                    end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
                    
        if not end_time:
            await ctx.send("❌ Invalid duration! Use format like: 5m, 1h, 1d", ephemeral=True)
            return
            
        # Create giveaway embed (no points deduction)
        embed = discord.Embed(
            title="🎁 POINTS GIVEAWAY!",
            description=f"**Prize:** {points} points\n\nReact with {emoji} to enter!",
            color=discord.Color.blue(),
            timestamp=end_time
        )
        embed.add_field(name="⏰ Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
        embed.add_field(name="👥 Entries", value="0", inline=True)
        embed.add_field(name="🎯 Host", value=ctx.author.mention, inline=True)
        embed.set_footer(text="React to enter • One entry per person")
        
        # Create view
        giveaway_id = f"{ctx.guild.id}_{ctx.channel.id}_{int(datetime.now().timestamp())}"
        view = GiveawayView(self, giveaway_id)
        
        # Send message
        message = await ctx.send(embed=embed, view=view)
        await message.add_reaction(emoji)
        
        # Store giveaway
        self.active_giveaways[giveaway_id] = {
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "message_id": message.id,
            "host_id": ctx.author.id,
            "prize": points,
            "emoji": emoji,
            "end_time": end_time,
            "entries": [],
            "created_at": datetime.now(timezone.utc)
        }
        
        # Log
        await self.log_action(
            ctx.guild.id,
            f"🎁 {ctx.author.mention} started a **{points}** points giveaway!",
            discord.Color.blue()
        )
        
        # Update entry count
        self.bot.loop.create_task(self.update_entry_count(giveaway_id))
    
    async def update_entry_count(self, giveaway_id: str):
        await asyncio.sleep(5)
        
        while giveaway_id in self.active_giveaways:
            giveaway = self.active_giveaways[giveaway_id]
            channel = self.bot.get_channel(giveaway["channel_id"])
            
            if not channel:
                break
                
            try:
                message = await channel.fetch_message(giveaway["message_id"])
                
                # Find reaction
                reaction = None
                for r in message.reactions:
                    if str(r.emoji) == giveaway["emoji"]:
                        reaction = r
                        break
                        
                if reaction:
                    # Count valid entries
                    valid_entries = 0
                    entry_list = []
                    
                    async for user in reaction.users():
                        if not user.bot and user.id != giveaway["host_id"]:
                            # Check if eligible
                            user_data = await self.db.users.find_one({"user_id": user.id})
                            if not user_data or user_data.get("blacklisted"):
                                # Remove reaction from blacklisted users
                                try:
                                    await message.remove_reaction(giveaway["emoji"], user)
                                except:
                                    pass
                                continue
                            valid_entries += 1
                            entry_list.append(user.id)
                    
                    # Update embed
                    embed = message.embeds[0]
                    embed.set_field_at(1, name="👥 Entries", value=str(valid_entries), inline=True)
                    await message.edit(embed=embed)
                    
                    # Update entry list
                    giveaway["entries"] = entry_list
                    
                # Remove non-matching reactions
                for reaction in message.reactions:
                    if str(reaction.emoji) != giveaway["emoji"]:
                        async for user in reaction.users():
                            if not user.bot:
                                try:
                                    await message.remove_reaction(reaction.emoji, user)
                                except:
                                    pass
                
            except:
                pass
                
            await asyncio.sleep(10)
    
    @pgiveaway.command(name="end", description="End active giveaway early (Owner only)")
    async def pgiveaway_end(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ Only the bot owner can manage giveaways!", ephemeral=True)
            return
            
        # Find active giveaway in this channel
        active_in_channel = None
        for gid, giveaway in self.active_giveaways.items():
            if giveaway["channel_id"] == ctx.channel.id:
                active_in_channel = gid
                break
                
        if not active_in_channel:
            await ctx.send("❌ No active giveaway in this channel!", ephemeral=True)
            return
            
        await self.end_giveaway(active_in_channel, manual=True)
        await ctx.send("✅ Giveaway ended!", ephemeral=True)
    
    @pgiveaway.command(name="list", description="List all active giveaways (Owner only)")
    async def pgiveaway_list(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ Only the bot owner can view giveaways!", ephemeral=True)
            return
            
        if not self.active_giveaways:
            await ctx.send("📭 No active giveaways!", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="🎁 Active Giveaways",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        for gid, giveaway in list(self.active_giveaways.items())[:10]:
            channel = self.bot.get_channel(giveaway["channel_id"])
            if channel:
                time_left = giveaway["end_time"] - datetime.now(timezone.utc)
                minutes = int(time_left.total_seconds() / 60)
                embed.add_field(
                    name=f"#{channel.name}",
                    value=f"Prize: **{giveaway['prize']}** points\n"
                          f"Entries: **{len(giveaway.get('entries', []))}**\n"
                          f"Ends in: **{minutes}** min",
                    inline=True
                )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))