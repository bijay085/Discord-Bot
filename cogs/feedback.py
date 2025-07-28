# cogs/feedback.py
# Location: cogs/feedback.py
# Description: Feedback system - fixed to remove duplicate messages and allow both photo + text feedback

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone
import traceback
from typing import Optional

class FeedbackModal(discord.ui.Modal):
    def __init__(self, cookie_type):
        super().__init__(title=f"Submit {cookie_type.title()} Cookie Feedback")
        self.cookie_type = cookie_type
        
        self.rating = discord.ui.TextInput(
            label="Rate this cookie (1-5 stars)",
            placeholder="Enter a number from 1 to 5",
            min_length=1,
            max_length=1,
            required=True
        )
        self.add_item(self.rating)
        
        self.feedback = discord.ui.TextInput(
            label="Your feedback (Screenshot still required!)",
            placeholder="Quick review here, then post screenshot in feedback channel for bonus points!",
            style=discord.TextStyle.paragraph,
            min_length=10,
            max_length=500,
            required=True
        )
        self.add_item(self.feedback)
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating.value)
            if rating < 1 or rating > 5:
                await interaction.response.send_message("❌ Rating must be between 1-5!", ephemeral=True)
                return
                
            cog = interaction.client.get_cog("FeedbackCog")
            if cog:
                await cog.process_feedback_submission(interaction, rating, self.feedback.value, self.cookie_type)
        except ValueError:
            await interaction.response.send_message("❌ Invalid rating! Enter a number 1-5", ephemeral=True)

class FeedbackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_feedback_deadlines.start()
        # Make FeedbackModal accessible from CookieCog
        self.FeedbackModal = FeedbackModal
        
    async def cog_unload(self):
        self.check_feedback_deadlines.cancel()
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def process_feedback_submission(self, interaction: discord.Interaction, rating: int, feedback: str, cookie_type: str = None):
        try:
            user_data = await self.db.users.find_one({"user_id": interaction.user.id})
            if not user_data or not user_data.get("last_claim"):
                await interaction.response.send_message("❌ No recent cookie claim found!", ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            # Check if COMPLETE feedback (photo + text) was already given
            if last_claim.get("feedback_given") and last_claim.get("rating"):
                await interaction.response.send_message("✅ You already submitted complete feedback!", ephemeral=True)
                return
            
            # Allow text feedback even if photo was submitted (but not if text was already submitted)
            if last_claim.get("rating"):
                await interaction.response.send_message("✅ You already submitted text feedback! Post a screenshot for bonus points.", ephemeral=True)
                return
            
            if cookie_type and last_claim.get("type") != cookie_type:
                await interaction.response.send_message("❌ This feedback doesn't match your last claim!", ephemeral=True)
                return
            
            current_streak = user_data.get("statistics", {}).get("feedback_streak", 0)
            
            if rating == 5:
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {"$inc": {"statistics.perfect_ratings": 1}}
                )
            
            # If photo was already submitted, this completes the feedback
            if last_claim.get("screenshot"):
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {
                        "$set": {
                            "last_claim.feedback_given": True,  # Now fully complete
                            "last_claim.rating": rating,
                            "last_claim.feedback_text": feedback
                        },
                        "$inc": {
                            "trust_score": 0.25  # Additional 0.25 for text
                        }
                    }
                )
                trust_text = "+0.25 points (Total: 0.75)"
                is_complete = True
            else:
                # Only text feedback so far
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {
                        "$set": {
                            "last_claim.feedback_given": False,  # Still need screenshot
                            "last_claim.rating": rating,
                            "last_claim.feedback_text": feedback,
                            "last_claim.text_feedback_only": True
                        },
                        "$inc": {
                            "trust_score": 0.25,  # 0.25 for text feedback
                            "statistics.feedback_streak": 1
                        }
                    }
                )
                trust_text = "+0.25 points"
                is_complete = False
            
            await self.db.feedback.insert_one({
                "user_id": interaction.user.id,
                "cookie_type": last_claim["type"],
                "file": last_claim["file"],
                "rating": rating,
                "feedback": feedback,
                "timestamp": datetime.now(timezone.utc),
                "server_id": interaction.guild_id,
                "has_screenshot": last_claim.get("screenshot", False)
            })
            
            stars = "⭐" * rating
            embed = discord.Embed(
                title="✅ Text Feedback Submitted!",
                description=f"Thank you for rating the **{last_claim['type']}** cookie!",
                color=discord.Color.green()
            )
            embed.add_field(name="Rating", value=stars, inline=True)
            embed.add_field(name="Trust Score", value=trust_text, inline=True)
            embed.add_field(name="Streak", value=f"{current_streak + 1} feedback(s)", inline=True)
            
            if not is_complete:
                server = await self.db.servers.find_one({"server_id": interaction.guild_id})
                if server and server.get("channels", {}).get("feedback"):
                    embed.add_field(
                        name="📸 Don't Forget!",
                        value=f"Post your screenshot in <#{server['channels']['feedback']}> for bonus points!",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="🎉 Complete!",
                    value="You've submitted both text and photo feedback!",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in process_feedback_submission: {e}")
            await interaction.response.send_message("❌ Error submitting feedback!", ephemeral=True)
    
    @tasks.loop(minutes=1)
    async def check_feedback_deadlines(self):
        try:
            now = datetime.now(timezone.utc)
            
            # Query only users with pending feedback and expired deadlines
            cursor = self.db.users.find({
                "last_claim.feedback_given": False,
                "last_claim.feedback_deadline": {"$lt": now},
                "blacklisted": False
            })
            
            # Process in batches to prevent memory issues
            batch = []
            async for user in cursor:
                batch.append(user)
                if len(batch) >= 10:
                    await self._process_deadline_batch(batch, now)
                    batch = []
            
            # Process remaining users
            if batch:
                await self._process_deadline_batch(batch, now)
                
        except Exception as e:
            print(f"Error in feedback check: {e}")
    
    async def _process_deadline_batch(self, users, now):
        for user in users:
            try:
                last_claim = user.get("last_claim")
                if last_claim and last_claim.get("feedback_deadline"):
                    # Get current trust score to ensure it doesn't go below 0
                    current_trust = user.get("trust_score", 50)
                    new_trust = max(0, current_trust - 1)
                    
                    await self.db.users.update_one(
                        {"user_id": user["user_id"]},
                        {
                            "$set": {
                                "blacklisted": True,
                                "blacklist_expires": now + timedelta(days=30),
                                "statistics.feedback_streak": 0,
                                "trust_score": new_trust
                            }
                        }
                    )
                    
                    guild_id = last_claim.get("server_id")
                    if guild_id:
                        await self.log_action(
                            guild_id,
                            f"🚫 <@{user['user_id']}> blacklisted for not providing feedback",
                            discord.Color.red()
                        )
                        
                        try:
                            user_obj = self.bot.get_user(user["user_id"])
                            if user_obj and user.get("preferences", {}).get("dm_notifications", True):
                                embed = discord.Embed(
                                    title="🚫 You've been blacklisted!",
                                    description="You failed to provide feedback within the deadline.",
                                    color=discord.Color.red()
                                )
                                embed.add_field(name="Duration", value="30 days", inline=True)
                                embed.add_field(name="Expires", value=f"<t:{int((now + timedelta(days=30)).timestamp())}:R>", inline=True)
                                await user_obj.send(embed=embed)
                        except:
                            pass
            except Exception as e:
                print(f"Error processing user {user.get('user_id')}: {e}")
    
    @commands.hybrid_command(name="feedback", description="Submit feedback with interactive form")
    async def feedback(self, ctx):
        try:
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            feedback_channel = server["channels"].get("feedback")
            if feedback_channel and ctx.channel.id != feedback_channel:
                embed = discord.Embed(
                    title="❌ Wrong Channel",
                    description=f"Please use <#{feedback_channel}> for feedback!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            if not user_data or not user_data.get("last_claim"):
                embed = discord.Embed(
                    title="❌ No Recent Claims",
                    description="You haven't claimed any cookies recently!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            # Check if complete feedback was given
            if last_claim.get("feedback_given") and last_claim.get("rating"):
                embed = discord.Embed(
                    title="✅ Already Submitted",
                    description="You've already submitted complete feedback for your last cookie!",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            deadline = last_claim["feedback_deadline"]
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            
            if datetime.now(timezone.utc) > deadline:
                embed = discord.Embed(
                    title="❌ Deadline Expired",
                    description="The feedback deadline has passed. You may be blacklisted.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            modal = FeedbackModal(last_claim["type"])
            
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.response.send_modal(modal)
            else:
                embed = discord.Embed(
                    title="📸 Submit Feedback",
                    description=f"Click the button below to submit feedback for your **{last_claim['type']}** cookie!",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="⏰ Deadline",
                    value=f"<t:{int(deadline.timestamp())}:R>",
                    inline=False
                )
                
                button = discord.ui.Button(
                    label="Submit Feedback",
                    style=discord.ButtonStyle.success,
                    emoji="📸"
                )
                
                async def button_callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("This isn't for you!", ephemeral=True)
                        return
                    await interaction.response.send_modal(modal)
                
                button.callback = button_callback
                view = discord.ui.View()
                view.add_item(button)
                
                await ctx.send(embed=embed, view=view, ephemeral=True)
                
        except Exception as e:
            print(f"Error in feedback command: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
            
        if message.attachments and message.channel.type == discord.ChannelType.text:
            try:
                server = await self.db.servers.find_one({"server_id": message.guild.id})
                if server and message.channel.id == server["channels"].get("feedback"):
                    user_data = await self.db.users.find_one({"user_id": message.author.id})
                    if user_data and user_data.get("last_claim"):
                        last_claim = user_data["last_claim"]
                        
                        # Check if already submitted screenshot
                        if last_claim.get("screenshot"):
                            return  # Already processed screenshot
                        
                        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                        has_image = any(att.filename.lower().endswith(ext) for att in message.attachments for ext in image_extensions)
                        
                        if has_image:
                            cookie_type = last_claim.get("type", "unknown")
                            
                            if last_claim.get("text_feedback_only"):
                                # User already submitted text feedback (0.25), this completes it
                                bonus = 0.5
                                embed_title = "🎉 Feedback Complete!"
                                trust_text = f"+{bonus} points (Total: 0.75)"
                                is_complete = True
                                
                                await self.db.users.update_one(
                                    {"user_id": message.author.id},
                                    {
                                        "$set": {
                                            "last_claim.feedback_given": True,
                                            "last_claim.screenshot": True
                                        },
                                        "$inc": {
                                            "trust_score": bonus
                                        }
                                    }
                                )
                            else:
                                # User is submitting screenshot without text feedback (only 0.5)
                                bonus = 0.5
                                embed_title = "📸 Screenshot Received!"
                                trust_text = f"+{bonus} points"
                                is_complete = False
                                
                                await self.db.users.update_one(
                                    {"user_id": message.author.id},
                                    {
                                        "$set": {
                                            "last_claim.screenshot": True
                                        },
                                        "$inc": {
                                            "trust_score": bonus,
                                            "statistics.feedback_streak": 1
                                        }
                                    }
                                )
                            
                            # Add reactions to the message
                            await message.add_reaction("✅")
                            await message.add_reaction("📸")
                            
                            # Send ephemeral follow-up if possible, otherwise DM
                            try:
                                embed = discord.Embed(
                                    title=embed_title,
                                    description=f"Thank you for the screenshot!",
                                    color=discord.Color.green()
                                )
                                embed.add_field(name="Trust Score", value=trust_text, inline=True)
                                embed.add_field(name="Cookie Type", value=cookie_type.title(), inline=True)
                                
                                if not is_complete:
                                    embed.add_field(
                                        name="💡 Tip",
                                        value="Use `/feedback` to add a text review for bonus points!",
                                        inline=False
                                    )
                                
                                await message.author.send(embed=embed)
                            except discord.Forbidden:
                                pass
                            
                            # Log to log channel (no public message in feedback channel)
                            if last_claim.get("rating"):
                                stars = "⭐" * last_claim["rating"]
                                feedback_text = f" - {last_claim.get('feedback_text', '')}" if last_claim.get('feedback_text') else ""
                                
                                await self.log_action(
                                    message.guild.id,
                                    f"📸 {message.author.mention} completed feedback for **{cookie_type}** cookie {stars}{feedback_text}",
                                    discord.Color.green()
                                )
                            else:
                                await self.log_action(
                                    message.guild.id,
                                    f"📸 {message.author.mention} submitted screenshot for **{cookie_type}** cookie",
                                    discord.Color.green()
                                )
                                
            except discord.HTTPException:
                # Handle failed message edits/sends
                pass
            except Exception as e:
                print(f"Error processing feedback attachment: {e}")

async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))