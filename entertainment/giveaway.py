import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
import re

class TimeExtendModal(discord.ui.Modal, title="Extend Giveaway Time"):
    time_input = discord.ui.TextInput(
        label="Additional Time",
        placeholder="Examples: 30m, 1h, 2d",
        required=True,
        max_length=10
    )
    
    def __init__(self, cog, giveaway_id):
        super().__init__()
        self.cog = cog
        self.giveaway_id = giveaway_id
        
    async def on_submit(self, interaction: discord.Interaction):
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        time_str = self.time_input.value.strip()
        
        # Parse time
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        unit = time_str[-1].lower()
        if unit in multipliers and time_str[:-1].isdigit():
            seconds = int(time_str[:-1]) * multipliers[unit]
            additional_time = timedelta(seconds=seconds)
        else:
            await interaction.response.send_message("❌ Invalid time format! Use: 30s, 5m, 1h, 2d", ephemeral=True)
            return
            
        old_time = giveaway["end_time"]
        giveaway["end_time"] += additional_time
        
        # Update the embed with new timestamp
        channel = self.cog.bot.get_channel(giveaway["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(giveaway["message_id"])
                embed = message.embeds[0]
                # Update both the timestamp and the field
                embed.timestamp = giveaway["end_time"]
                embed.set_field_at(0, name="⏰ Ends", value=f"<t:{int(giveaway['end_time'].timestamp())}:R>", inline=True)
                await message.edit(embed=embed)
                
                await interaction.response.send_message(
                    f"✅ **Giveaway Extended!**\n"
                    f"Added **{time_str}** to the timer\n"
                    f"New end time: <t:{int(giveaway['end_time'].timestamp())}:F>", 
                    ephemeral=True
                )
                
                # Announce in channel
                announce_embed = discord.Embed(
                    title="⏰ Giveaway Extended!",
                    description=f"The giveaway has been extended by **{time_str}**!\n"
                               f"New end time: <t:{int(giveaway['end_time'].timestamp())}:R>",
                    color=discord.Color.blue()
                )
                await channel.send(embed=announce_embed, delete_after=10)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to update: {e}", ephemeral=True)

class GiveawayView(discord.ui.View):
    def __init__(self, cog, giveaway_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id
        
    @discord.ui.button(label="End Early", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def end_early(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Owner only
        if not await self.cog.is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Only the bot owner can end giveaways!", ephemeral=True)
            return
            
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.cog.end_giveaway(self.giveaway_id, manual=True)
        
    @discord.ui.button(label="Add Time", style=discord.ButtonStyle.primary, emoji="⏰", row=0)
    async def add_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Owner only
        if not await self.cog.is_owner(interaction.user.id):
            await interaction.response.send_message("❌ Only the bot owner can extend giveaways!", ephemeral=True)
            return
            
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        modal = TimeExtendModal(self.cog, self.giveaway_id)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Participants", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def show_participants(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Anyone can view
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        entries = giveaway.get("entries", [])
        if not entries:
            await interaction.response.send_message("📭 **No participants yet!**\nBe the first to enter!", ephemeral=True)
            return
            
        participant_list = []
        for i, user_id in enumerate(entries[:25], 1):
            user = self.cog.bot.get_user(user_id)
            if user:
                participant_list.append(f"`{i:02d}.` {user.mention}")
                
        embed = discord.Embed(
            title="👥 Giveaway Participants",
            description="\n".join(participant_list) + (f"\n\n*And {len(entries) - 25} more...*" if len(entries) > 25 else ""),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Total: {len(entries)} participants • Prize: {giveaway['prize']} points")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @discord.ui.button(label="Info", style=discord.ButtonStyle.success, emoji="ℹ️", row=1)
    async def show_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Anyone can view
        giveaway = self.cog.active_giveaways.get(self.giveaway_id)
        if not giveaway:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return
            
        host = self.cog.bot.get_user(giveaway["host_id"])
        time_left = giveaway["end_time"] - datetime.now(timezone.utc)
        
        embed = discord.Embed(
            title="ℹ️ Giveaway Information",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎁 Prize", value=f"{giveaway['prize']} points", inline=True)
        embed.add_field(name="🎯 Host", value=host.mention if host else "Unknown", inline=True)
        embed.add_field(name="👥 Entries", value=str(len(giveaway.get("entries", []))), inline=True)
        embed.add_field(name="⏰ Time Left", value=f"{int(time_left.total_seconds() / 60)} minutes", inline=True)
        embed.add_field(name="🏆 Winners", value=str(giveaway.get("winners", 1)), inline=True)
        embed.add_field(name="📅 Started", value=f"<t:{int(giveaway['created_at'].timestamp())}:R>", inline=True)
        
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
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction adds for giveaway entries"""
        if payload.user_id == self.bot.user.id:
            return
            
        # Check all active giveaways
        for gid, giveaway in self.active_giveaways.items():
            if giveaway["message_id"] == payload.message_id and str(payload.emoji) == giveaway["emoji"]:
                # Found matching giveaway
                channel = self.bot.get_channel(payload.channel_id)
                user = self.bot.get_user(payload.user_id)
                
                if not channel or not user:
                    return
                
                # Check if user is blacklisted
                user_data = await self.db.users.find_one({"user_id": payload.user_id})
                if user_data and user_data.get("blacklisted"):
                    try:
                        message = await channel.fetch_message(payload.message_id)
                        await message.remove_reaction(payload.emoji, user)
                        await user.send("❌ You are blacklisted and cannot enter giveaways!")
                    except:
                        pass
                    return
                
                if payload.user_id not in giveaway["entries"]:
                    giveaway["entries"].append(payload.user_id)
                    
                    # Update embed
                    try:
                        message = await channel.fetch_message(payload.message_id)
                        embed = message.embeds[0]
                        embed.set_field_at(1, name="👥 Entries", value=str(len(giveaway["entries"])), inline=True)
                        await message.edit(embed=embed)
                        
                        # Send confirmation message
                        confirm_embed = discord.Embed(
                            title="✅ Entry Confirmed!",
                            description=f"{user.mention} entered the giveaway for **{giveaway['prize']}** points!",
                            color=discord.Color.green()
                        )
                        confirm_embed.add_field(name="📊 Entry #", value=str(len(giveaway['entries'])), inline=True)
                        confirm_embed.add_field(name="⏰ Ends", value=f"<t:{int(giveaway['end_time'].timestamp())}:R>", inline=True)
                        confirm_embed.set_footer(text="Good luck! 🍀")
                        
                        await channel.send(
                            embed=confirm_embed,
                            delete_after=5
                        )
                    except Exception as e:
                        print(f"Error updating giveaway: {e}")
                else:
                    # Already entered
                    try:
                        await channel.send(
                            f"❗ {user.mention} is already in the giveaway!",
                            delete_after=3
                        )
                    except:
                        pass
                break
                    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle reaction removes for giveaway entries"""
        for gid, giveaway in self.active_giveaways.items():
            if giveaway["message_id"] == payload.message_id and str(payload.emoji) == giveaway["emoji"]:
                if payload.user_id in giveaway["entries"]:
                    giveaway["entries"].remove(payload.user_id)
                    
                    # Update embed
                    channel = self.bot.get_channel(payload.channel_id)
                    if channel:
                        try:
                            message = await channel.fetch_message(payload.message_id)
                            embed = message.embeds[0]
                            embed.set_field_at(1, name="👥 Entries", value=str(len(giveaway["entries"])), inline=True)
                            await message.edit(embed=embed)
                            
                            user = self.bot.get_user(payload.user_id)
                            if user:
                                await channel.send(
                                    f"👋 {user.mention} left the giveaway!",
                                    delete_after=3
                                )
                        except Exception as e:
                            print(f"Error updating embed: {e}")
                break
            
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
            
        entries = giveaway.get("entries", [])
        num_winners = giveaway.get("winners", 1)
        
        if entries:
            # Pick winners
            winners = []
            winner_mentions = []
            
            num_to_pick = min(num_winners, len(entries))
            selected = random.sample(entries, num_to_pick)
            
            for winner_id in selected:
                winner = self.bot.get_user(winner_id)
                if winner:
                    winners.append(winner)
                    winner_mentions.append(winner.mention)
                    
                    # Award points
                    await self.db.users.update_one(
                        {"user_id": winner_id},
                        {
                            "$inc": {"points": giveaway["prize"]},
                            "$set": {"last_active": datetime.now(timezone.utc)}
                        },
                        upsert=True
                    )
                    
                    # DM winner
                    try:
                        dm_embed = discord.Embed(
                            title="🎉 CONGRATULATIONS! YOU WON!",
                            description=f"You won **{giveaway['prize']}** points in {channel.guild.name}!",
                            color=discord.Color.gold()
                        )
                        dm_embed.add_field(name="💰 Prize", value=f"{giveaway['prize']} points", inline=True)
                        dm_embed.add_field(name="📍 Server", value=channel.guild.name, inline=True)
                        dm_embed.set_thumbnail(url=channel.guild.icon.url if channel.guild.icon else None)
                        dm_embed.set_footer(text="The points have been added to your account!")
                        await winner.send(embed=dm_embed)
                    except:
                        pass
            
            if winners:
                # Update original message
                embed = discord.Embed(
                    title="🎉 GIVEAWAY ENDED!",
                    description=f"**Winner{'s' if len(winners) > 1 else ''}:** {', '.join(winner_mentions)}\n"
                               f"**Prize:** {giveaway['prize']} points{' each' if len(winners) > 1 else ''}",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="👥 Total Entries", value=str(len(entries)), inline=True)
                embed.add_field(name="🎁 Prize Claimed", value="✅", inline=True)
                embed.add_field(name="🏆 Winners", value=str(len(winners)), inline=True)
                embed.set_footer(text=f"Hosted by {self.bot.get_user(giveaway['host_id'])}")
                
                await message.edit(embed=embed, view=None)
                
                # Send celebration message
                celebrate_embed = discord.Embed(
                    title="🎊 CONGRATULATIONS TO THE WINNER" + ("S" if len(winners) > 1 else "") + "!",
                    description=f"## {', '.join(winner_mentions)}\n\n"
                               f"You {'have each' if len(winners) > 1 else 'have'} won **{giveaway['prize']}** points! 🎉",
                    color=discord.Color.gold()
                )
                celebrate_embed.set_image(url="https://media.giphy.com/media/g9582DNuQppxC/giphy.gif")
                await channel.send(embed=celebrate_embed)
                
                await self.log_action(
                    channel.guild.id,
                    f"🎁 Giveaway ended! {', '.join(winner_mentions)} won **{giveaway['prize']}** points",
                    discord.Color.gold()
                )
        else:
            embed = discord.Embed(
                title="😢 GIVEAWAY ENDED",
                description="No valid entries! Nobody won the prize.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text="Better luck next time!")
            
            await message.edit(embed=embed, view=None)
            await channel.send("💔 **No one entered the giveaway!** The prize goes unclaimed...")
        
        del self.active_giveaways[giveaway_id]
    
    @commands.hybrid_group(name="pgiveaway", description="Points giveaway system")
    async def pgiveaway(self, ctx):
        # Remove this - no base command needed
        pass
    
    @pgiveaway.command(name="start", description="Start a points giveaway (Owner only)")
    @app_commands.describe(
        points="Amount of points to give away",
        duration="Duration (e.g., 5m, 1h, 1d)",
        winners="Number of winners (default: 1)"
    )
    async def pgiveaway_start(self, ctx, points: int, duration: Optional[str] = "5m", winners: Optional[int] = 1):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ Only the bot owner can create giveaways!", ephemeral=True)
            return
            
        if points <= 0:
            await ctx.send("❌ Points must be positive!", ephemeral=True)
            return
            
        if winners < 1:
            await ctx.send("❌ Must have at least 1 winner!", ephemeral=True)
            return
            
        # Parse duration
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        unit = duration[-1].lower()
        if unit in multipliers and duration[:-1].isdigit():
            seconds = int(duration[:-1]) * multipliers[unit]
            end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        else:
            await ctx.send("❌ Invalid duration! Use format like: 5m, 1h, 1d", ephemeral=True)
            return
            
        emoji = "🎉"
        
        # Create embed
        embed = discord.Embed(
            title="🎁 POINTS GIVEAWAY!",
            description=f"## Prize: {points} points{' each' if winners > 1 else ''}\n"
                       f"## Winners: {winners} {'winners' if winners > 1 else 'winner'}\n\n"
                       f"React with {emoji} to enter!",
            color=discord.Color.blue(),
            timestamp=end_time
        )
        embed.add_field(name="⏰ Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
        embed.add_field(name="👥 Entries", value="0", inline=True)
        embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
        embed.set_footer(text=f"Hosted by {ctx.author} • React to enter!")
        
        # Create view
        giveaway_id = f"{ctx.guild.id}_{ctx.channel.id}_{int(datetime.now().timestamp())}"
        view = GiveawayView(self, giveaway_id)
        
        # Send message
        await ctx.defer()
        message = await ctx.send(embed=embed, view=view)
        await message.add_reaction(emoji)
        
        # Store giveaway data
        self.active_giveaways[giveaway_id] = {
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "message_id": message.id,
            "host_id": ctx.author.id,
            "prize": points,
            "winners": winners,
            "emoji": emoji,
            "end_time": end_time,
            "entries": [],
            "created_at": datetime.now(timezone.utc)
        }
        
        # Send confirmation
        start_embed = discord.Embed(
            title="🎉 Giveaway Started!",
            description=f"**Prize:** {points} points{' each' if winners > 1 else ''}\n"
                       f"**Winners:** {winners}\n"
                       f"**Duration:** {duration}\n"
                       f"**Ends:** <t:{int(end_time.timestamp())}:F>",
            color=discord.Color.green()
        )
        await ctx.channel.send(embed=start_embed, delete_after=10)
        
        await self.log_action(
            ctx.guild.id,
            f"🎁 {ctx.author.mention} started a **{points}** points giveaway for {winners} winner{'s' if winners > 1 else ''}!",
            discord.Color.blue()
        )
    
    @pgiveaway.command(name="list", description="List all active giveaways (Owner only)")
    async def pgiveaway_list(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ Only the bot owner can view giveaways!", ephemeral=True)
            return
            
        if not self.active_giveaways:
            embed = discord.Embed(
                title="📭 No Active Giveaways",
                description="There are no active giveaways right now.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
            
        embed = discord.Embed(
            title="🎁 Active Giveaways",
            description=f"Currently running: **{len(self.active_giveaways)}** giveaway{'s' if len(self.active_giveaways) > 1 else ''}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        for i, (gid, giveaway) in enumerate(list(self.active_giveaways.items())[:10], 1):
            channel = self.bot.get_channel(giveaway["channel_id"])
            if channel:
                time_left = giveaway["end_time"] - datetime.now(timezone.utc)
                minutes = int(time_left.total_seconds() / 60)
                
                embed.add_field(
                    name=f"{i}. {channel.guild.name} - #{channel.name}",
                    value=f"💰 **Prize:** {giveaway['prize']} points\n"
                          f"🏆 **Winners:** {giveaway.get('winners', 1)}\n"
                          f"👥 **Entries:** {len(giveaway.get('entries', []))}\n"
                          f"⏰ **Ends in:** {minutes} minutes",
                    inline=False
                )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))