# cogs/events.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import random
import asyncio
from typing import Optional, List

class EventView(discord.ui.View):
    def __init__(self, event_type: str, participants: List[int] = None):
        super().__init__(timeout=300)
        self.event_type = event_type
        self.participants = participants or []
        
    @discord.ui.button(label="🎯 Join Event", style=discord.ButtonStyle.success)
    async def join_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            await interaction.response.send_message("✅ You're already in this event!", ephemeral=True)
            return
            
        self.participants.append(interaction.user.id)
        await interaction.response.send_message("✅ Successfully joined the event!", ephemeral=True)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(
            0,
            name="👥 Participants",
            value=f"**{len(self.participants)}** joined",
            inline=True
        )
        await interaction.message.edit(embed=embed)
        
    @discord.ui.button(label="📋 View Participants", style=discord.ButtonStyle.secondary)
    async def view_participants(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.participants:
            await interaction.response.send_message("❌ No participants yet!", ephemeral=True)
            return
            
        participant_list = []
        for i, user_id in enumerate(self.participants[:20]):
            user = interaction.client.get_user(user_id)
            participant_list.append(f"`{i+1}.` {user.mention if user else 'Unknown'}")
            
        embed = discord.Embed(
            title="📋 Event Participants",
            description="\n".join(participant_list),
            color=0x5865f2
        )
        if len(self.participants) > 20:
            embed.set_footer(text=f"Showing 20 of {len(self.participants)} participants")
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

class GiveawayView(discord.ui.View):
    def __init__(self, prize: str, host_id: int, duration: int):
        super().__init__(timeout=duration)
        self.prize = prize
        self.host_id = host_id
        self.participants = []
        self.ended = False
        
    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.primary, emoji="🎟️")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.ended:
            await interaction.response.send_message("❌ This giveaway has ended!", ephemeral=True)
            return
            
        if interaction.user.id in self.participants:
            await interaction.response.send_message("✅ You're already entered!", ephemeral=True)
            return
            
        if interaction.user.id == self.host_id:
            await interaction.response.send_message("❌ Hosts cannot enter their own giveaway!", ephemeral=True)
            return
            
        self.participants.append(interaction.user.id)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(
            1,
            name="🎟️ Entries",
            value=f"**{len(self.participants)}**",
            inline=True
        )
        
        await interaction.response.edit_message(embed=embed)
        await interaction.followup.send("✅ You've entered the giveaway! Good luck! 🍀", ephemeral=True)
    
    async def on_timeout(self):
        self.ended = True
        for item in self.children:
            item.disabled = True

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_events.start()
        self.cookie_drop.start()
        self.daily_trivia.start()
        
    def cog_unload(self):
        self.check_events.cancel()
        self.cookie_drop.cancel()
        self.daily_trivia.cancel()
        
    @tasks.loop(minutes=1)
    async def check_events(self):
        try:
            now = datetime.now(timezone.utc)
            
            ending_events = await self.db.events.find({
                "active": True,
                "end_time": {"$lte": now}
            }).to_list(None)
            
            for event in ending_events:
                await self.end_event(event)
                
        except Exception as e:
            self.bot.logger.error(f"Error checking events: {e}")
    
    @tasks.loop(hours=random.randint(2, 6))
    async def cookie_drop(self):
        try:
            active_servers = await self.db.servers.find({
                "enabled": True,
                "channels.cookie": {"$exists": True}
            }).to_list(None)
            
            if not active_servers:
                return
                
            server = random.choice(active_servers)
            channel_id = server["channels"].get("cookie")
            if not channel_id:
                return
                
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
                
            drop_amount = random.randint(10, 50)
            
            embed = discord.Embed(
                title="🍪 Cookie Drop!",
                description=f"**{drop_amount}** points have been dropped!\nFirst person to click gets them!",
                color=0xffd700,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text="Cookie Bot Events")
            
            view = discord.ui.View(timeout=60)
            button = discord.ui.Button(
                label="🍪 Claim Drop",
                style=discord.ButtonStyle.success
            )
            
            claimed = False
            
            async def claim_callback(interaction: discord.Interaction):
                nonlocal claimed
                if claimed:
                    await interaction.response.send_message("❌ Already claimed!", ephemeral=True)
                    return
                    
                claimed = True
                
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {
                        "$inc": {"points": drop_amount},
                        "$setOnInsert": {
                            "username": str(interaction.user),
                            "total_earned": 0,
                            "total_spent": 0
                        }
                    },
                    upsert=True
                )
                
                success_embed = discord.Embed(
                    title="🍪 Cookie Drop Claimed!",
                    description=f"{interaction.user.mention} claimed **{drop_amount}** points!",
                    color=0x00ff00,
                    timestamp=datetime.now(timezone.utc)
                )
                
                button.disabled = True
                await interaction.response.edit_message(embed=success_embed, view=view)
                
            button.callback = claim_callback
            view.add_item(button)
            
            await channel.send(embed=embed, view=view)
            
        except Exception as e:
            self.bot.logger.error(f"Error in cookie drop: {e}")
    
    @tasks.loop(hours=24)
    async def daily_trivia(self):
        try:
            trivia_questions = [
                {
                    "question": "What year was Discord founded?",
                    "answers": ["2015"],
                    "reward": 25
                },
                {
                    "question": "How many cookies can you claim per day with the free role?",
                    "answers": ["depends", "varies", "unlimited with cooldown"],
                    "reward": 20
                },
                {
                    "question": "What's the maximum trust score?",
                    "answers": ["100"],
                    "reward": 30
                }
            ]
            
            active_servers = await self.db.servers.find({
                "enabled": True,
                "channels.announcement": {"$exists": True}
            }).to_list(None)
            
            if not active_servers:
                return
                
            question = random.choice(trivia_questions)
            
            for server in active_servers:
                channel_id = server["channels"].get("announcement")
                if not channel_id:
                    continue
                    
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue
                    
                await self.create_trivia_event(channel, question)
                
        except Exception as e:
            self.bot.logger.error(f"Error in daily trivia: {e}")
    
    async def create_trivia_event(self, channel: discord.TextChannel, question: dict):
        embed = discord.Embed(
            title="🧠 Daily Trivia Challenge!",
            description=f"**Question:** {question['question']}\n\nFirst correct answer wins **{question['reward']}** points!",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Type your answer in chat!")
        
        message = await channel.send(embed=embed)
        
        def check(m):
            return m.channel == channel and any(
                answer.lower() in m.content.lower() 
                for answer in question['answers']
            )
        
        try:
            winner_msg = await self.bot.wait_for('message', check=check, timeout=300)
            
            await self.db.users.update_one(
                {"user_id": winner_msg.author.id},
                {
                    "$inc": {"points": question['reward']},
                    "$setOnInsert": {
                        "username": str(winner_msg.author),
                        "total_earned": 0,
                        "total_spent": 0
                    }
                },
                upsert=True
            )
            
            winner_embed = discord.Embed(
                title="🏆 Trivia Winner!",
                description=f"{winner_msg.author.mention} got it right and won **{question['reward']}** points!",
                color=0x00ff00
            )
            winner_embed.add_field(name="Answer", value=winner_msg.content, inline=False)
            
            await channel.send(embed=winner_embed, reference=winner_msg)
            
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="⏰ Trivia Timeout",
                description=f"Nobody got the answer in time!\nCorrect answer: **{question['answers'][0]}**",
                color=0xff0000
            )
            await channel.send(embed=timeout_embed)

    @commands.hybrid_command(name="event", description="Create a special event")
    @commands.has_permissions(manage_events=True)
    async def create_event(self, ctx, event_type: str, duration: str = "1h", *, details: str = None):
        valid_types = ["double_points", "free_cookies", "trivia_marathon", "cookie_hunt"]
        
        if event_type not in valid_types:
            await ctx.send(f"❌ Invalid event type! Choose from: {', '.join(valid_types)}", ephemeral=True)
            return
        
        time_units = {"m": 60, "h": 3600, "d": 86400}
        unit = duration[-1].lower()
        if unit not in time_units:
            await ctx.send("❌ Invalid duration! Use: 1m, 1h, 1d", ephemeral=True)
            return
            
        try:
            amount = int(duration[:-1])
            seconds = amount * time_units[unit]
        except:
            await ctx.send("❌ Invalid duration format!", ephemeral=True)
            return
        
        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        
        event_data = {
            "guild_id": ctx.guild.id,
            "type": event_type,
            "details": details,
            "created_by": ctx.author.id,
            "start_time": datetime.now(timezone.utc),
            "end_time": end_time,
            "active": True,
            "participants": []
        }
        
        event_id = await self.db.events.insert_one(event_data)
        
        embed = discord.Embed(
            title=f"🎉 {event_type.replace('_', ' ').title()} Event!",
            description=details or self.get_event_description(event_type),
            color=0xffd700,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👥 Participants", value="**0** joined", inline=True)
        embed.add_field(name="⏰ Duration", value=duration, inline=True)
        embed.add_field(name="🏁 Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
        embed.set_footer(text=f"Event ID: {event_id.inserted_id}")
        
        view = EventView(event_type)
        await ctx.send(embed=embed, view=view)
        
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(
                ctx.guild.id,
                f"🎉 {ctx.author.mention} started a **{event_type}** event for {duration}",
                discord.Color.gold()
            )
    
    def get_event_description(self, event_type: str) -> str:
        descriptions = {
            "double_points": "All point rewards are doubled during this event!",
            "free_cookies": "Cookie costs are reduced by 50%!",
            "trivia_marathon": "Answer trivia questions to earn bonus points!",
            "cookie_hunt": "Find hidden cookies around the server!"
        }
        return descriptions.get(event_type, "Special event is active!")
    
    async def end_event(self, event: dict):
        await self.db.events.update_one(
            {"_id": event["_id"]},
            {"$set": {"active": False}}
        )
        
        guild = self.bot.get_guild(event["guild_id"])
        if not guild:
            return
            
        server = await self.db.servers.find_one({"server_id": guild.id})
        if not server:
            return
            
        announcement_channel = guild.get_channel(server["channels"].get("announcement"))
        if announcement_channel:
            embed = discord.Embed(
                title="🏁 Event Ended!",
                description=f"The **{event['type'].replace('_', ' ').title()}** event has ended!",
                color=0xff6600,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(
                name="📊 Stats",
                value=f"Participants: **{len(event.get('participants', []))}**",
                inline=True
            )
            
            await announcement_channel.send(embed=embed)

    @commands.hybrid_command(name="giveaway", description="Start a giveaway")
    @commands.has_permissions(manage_events=True)
    async def giveaway(self, ctx, duration: str, winners: int, *, prize: str):
        time_units = {"m": 60, "h": 3600, "d": 86400}
        unit = duration[-1].lower()
        if unit not in time_units:
            await ctx.send("❌ Invalid duration! Use: 1m, 1h, 1d", ephemeral=True)
            return
            
        try:
            amount = int(duration[:-1])
            seconds = amount * time_units[unit]
            if seconds > 604800:  # 7 days
                await ctx.send("❌ Maximum giveaway duration is 7 days!", ephemeral=True)
                return
        except:
            await ctx.send("❌ Invalid duration format!", ephemeral=True)
            return
        
        if winners < 1 or winners > 20:
            await ctx.send("❌ Winners must be between 1 and 20!", ephemeral=True)
            return
        
        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"**Prize:** {prize}",
            color=0xffd700,
            timestamp=end_time
        )
        embed.add_field(name="🏆 Winners", value=f"**{winners}**", inline=True)
        embed.add_field(name="🎟️ Entries", value="**0**", inline=True)
        embed.add_field(name="⏰ Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
        embed.set_footer(text=f"Hosted by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        view = GiveawayView(prize, ctx.author.id, seconds)
        message = await ctx.send(embed=embed, view=view)
        
        giveaway_data = {
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "message_id": message.id,
            "host_id": ctx.author.id,
            "prize": prize,
            "winners_count": winners,
            "end_time": end_time,
            "active": True
        }
        
        giveaway_id = await self.db.giveaways.insert_one(giveaway_data)
        
        await asyncio.sleep(seconds)
        
        await self.end_giveaway(giveaway_id.inserted_id, message, view.participants)
    
    async def end_giveaway(self, giveaway_id, message: discord.Message, participants: List[int]):
        giveaway = await self.db.giveaways.find_one({"_id": giveaway_id})
        if not giveaway:
            return
        
        await self.db.giveaways.update_one(
            {"_id": giveaway_id},
            {"$set": {"active": False, "participants": participants}}
        )
        
        if not participants:
            embed = discord.Embed(
                title="🎉 Giveaway Ended",
                description=f"**Prize:** {giveaway['prize']}\n\nNo participants entered!",
                color=0xff0000
            )
            await message.edit(embed=embed, view=None)
            return
        
        winners_count = min(giveaway["winners_count"], len(participants))
        winners = random.sample(participants, winners_count)
        
        winner_mentions = [f"<@{winner_id}>" for winner_id in winners]
        
        embed = discord.Embed(
            title="🎉 Giveaway Ended!",
            description=f"**Prize:** {giveaway['prize']}",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name="🏆 Winner(s)",
            value="\n".join(winner_mentions),
            inline=False
        )
        embed.add_field(name="🎟️ Total Entries", value=len(participants), inline=True)
        embed.set_footer(text=f"Hosted by {message.guild.get_member(giveaway['host_id'])}")
        
        await message.edit(embed=embed, view=None)
        await message.reply(f"Congratulations {', '.join(winner_mentions)}! 🎉")
        
        for winner_id in winners:
            try:
                winner = self.bot.get_user(winner_id)
                if winner:
                    dm_embed = discord.Embed(
                        title="🎉 You Won a Giveaway!",
                        description=f"You won **{giveaway['prize']}** in {message.guild.name}!",
                        color=0x00ff00
                    )
                    await winner.send(embed=dm_embed)
            except:
                pass

    @commands.hybrid_command(name="reroll", description="Reroll giveaway winners")
    @commands.has_permissions(manage_events=True)
    async def reroll(self, ctx, message_id: str):
        try:
            message_id = int(message_id)
            giveaway = await self.db.giveaways.find_one({
                "message_id": message_id,
                "guild_id": ctx.guild.id,
                "active": False
            })
            
            if not giveaway:
                await ctx.send("❌ Giveaway not found or still active!", ephemeral=True)
                return
            
            participants = giveaway.get("participants", [])
            if not participants:
                await ctx.send("❌ No participants in this giveaway!", ephemeral=True)
                return
            
            winners_count = min(giveaway["winners_count"], len(participants))
            new_winners = random.sample(participants, winners_count)
            
            winner_mentions = [f"<@{winner_id}>" for winner_id in new_winners]
            
            embed = discord.Embed(
                title="🎲 Giveaway Rerolled!",
                description=f"**New Winner(s):** {', '.join(winner_mentions)}",
                color=0x5865f2
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {e}", ephemeral=True)

    @commands.hybrid_command(name="active_events", description="View all active events")
    async def active_events(self, ctx):
        events = await self.db.events.find({
            "guild_id": ctx.guild.id,
            "active": True
        }).to_list(10)
        
        giveaways = await self.db.giveaways.find({
            "guild_id": ctx.guild.id,
            "active": True
        }).to_list(10)
        
        if not events and not giveaways:
            embed = discord.Embed(
                title="📅 No Active Events",
                description="There are no active events or giveaways right now!",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📅 Active Events & Giveaways",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        if events:
            event_text = []
            for event in events[:5]:
                event_text.append(
                    f"• **{event['type'].replace('_', ' ').title()}**\n"
                    f"  Ends: <t:{int(event['end_time'].timestamp())}:R>"
                )
            embed.add_field(
                name="🎉 Events",
                value="\n".join(event_text),
                inline=False
            )
        
        if giveaways:
            giveaway_text = []
            for giveaway in giveaways[:5]:
                giveaway_text.append(
                    f"• **{giveaway['prize'][:30]}{'...' if len(giveaway['prize']) > 30 else ''}**\n"
                    f"  Winners: {giveaway['winners_count']} | Ends: <t:{int(giveaway['end_time'].timestamp())}:R>"
                )
            embed.add_field(
                name="🎁 Giveaways",
                value="\n".join(giveaway_text),
                inline=False
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))