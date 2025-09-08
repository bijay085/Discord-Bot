import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone
import traceback
from typing import Optional
import asyncio
import random

class QuickFeedbackView(discord.ui.View):
    """Quick one-click feedback options"""
    def __init__(self, cookie_type, user_id, cog):
        super().__init__(timeout=900)  # 15 minutes
        self.cookie_type = cookie_type
        self.user_id = user_id
        self.cog = cog
        
    @discord.ui.button(label="Works Perfect!", style=discord.ButtonStyle.success, emoji="⭐", row=0)
    async def five_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your feedback menu!", ephemeral=True)
            return
        await self.quick_submit(interaction, 5, f"The {self.cookie_type} cookie works perfectly! All features are accessible and working great.")
        
    @discord.ui.button(label="Good", style=discord.ButtonStyle.primary, emoji="👍", row=0)
    async def four_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your feedback menu!", ephemeral=True)
            return
        await self.quick_submit(interaction, 4, f"The {self.cookie_type} cookie works well! Minor issues but overall satisfied.")
        
    @discord.ui.button(label="Okay", style=discord.ButtonStyle.secondary, emoji="👌", row=0)
    async def three_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your feedback menu!", ephemeral=True)
            return
        await self.quick_submit(interaction, 3, f"The {self.cookie_type} cookie works okay. Some features work, some don't.")
        
    @discord.ui.button(label="Has Issues", style=discord.ButtonStyle.secondary, emoji="⚠️", row=1)
    async def two_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your feedback menu!", ephemeral=True)
            return
        await self.quick_submit(interaction, 2, f"The {self.cookie_type} cookie has issues. Many features not working properly.")
        
    @discord.ui.button(label="Not Working", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def one_star(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your feedback menu!", ephemeral=True)
            return
        await self.quick_submit(interaction, 1, f"The {self.cookie_type} cookie is not working. Cannot access the service.")
        
    @discord.ui.button(label="Write Custom Feedback", style=discord.ButtonStyle.secondary, emoji="✏️", row=2)
    async def custom_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your feedback menu!", ephemeral=True)
            return
        modal = FeedbackModal(self.cookie_type)
        await interaction.response.send_modal(modal)
            
    async def quick_submit(self, interaction: discord.Interaction, rating: int, feedback: str):
        await interaction.response.defer(ephemeral=True)
        await self.cog.process_quick_feedback(interaction, rating, feedback, self.cookie_type)

class FeedbackModal(discord.ui.Modal):
    def __init__(self, cookie_type):
        super().__init__(title=f"Rate Your {cookie_type.title()} Cookie")
        self.cookie_type = cookie_type
        
        self.rating = discord.ui.TextInput(
            label=f"Rating (1-5 stars)",
            placeholder="Enter 1 for worst, 5 for best",
            min_length=1,
            max_length=1,
            required=True
        )
        self.add_item(self.rating)
        
        self.feedback = discord.ui.TextInput(
            label="Your detailed feedback",
            placeholder=f"Tell us about your {cookie_type} experience! Any issues or compliments?",
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
                await interaction.response.send_message(
                    "❌ Please enter a number between 1 and 5!", 
                    ephemeral=True
                )
                return
                
            await interaction.response.defer(ephemeral=True)
            
            cog = interaction.client.get_cog("FeedbackCog")
            if cog:
                await cog.process_feedback_submission(
                    interaction, rating, self.feedback.value, self.cookie_type
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number (1-5)!", 
                ephemeral=True
            )

class FeedbackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_feedback_deadlines.start()
        self.send_feedback_reminders.start()
        self.FeedbackModal = FeedbackModal
        
    async def cog_unload(self):
        self.check_feedback_deadlines.cancel()
        self.send_feedback_reminders.cancel()
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def get_user_role_config(self, member: discord.Member, server: dict) -> dict:
        if not server.get("role_based"):
            return {}
            
        best_config = {}
        highest_priority = -1
        
        server = await self.db.servers.find_one({"server_id": member.guild.id})
        if not server or not server.get("roles"):
            return {}
        
        for role in member.roles:
            role_config = server["roles"].get(str(role.id))
            if role_config and isinstance(role_config, dict):
                if role.position > highest_priority:
                    highest_priority = role.position
                    best_config = role_config
        
        return best_config
    
    async def add_instant_feedback_to_dm(self, dm_message, cookie_type: str, user_id: int):
        """Add quick feedback buttons to cookie delivery DM"""
        view = QuickFeedbackView(cookie_type, user_id, self)
        await dm_message.edit(view=view)
        return view
    
    async def process_quick_feedback(self, interaction: discord.Interaction, rating: int, feedback: str, cookie_type: str):
        """Process feedback from quick buttons"""
        try:
            user_data = await self.db.users.find_one({"user_id": interaction.user.id})
            if not user_data or not user_data.get("last_claim"):
                await interaction.followup.send("❌ No recent cookie claim found!", ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            # Check what's already submitted
            has_text_feedback = last_claim.get("rating") is not None
            has_screenshot = last_claim.get("screenshot", False)
            
            if has_text_feedback and has_screenshot:
                await interaction.followup.send(
                    "✅ **You're all done!** Both feedback and screenshot already submitted! 🎉",
                    ephemeral=True
                )
                return
            
            if has_text_feedback:
                await interaction.followup.send(
                    f"✅ **Rating already submitted!**\n"
                    f"📸 Just need a screenshot in the feedback channel to complete!",
                    ephemeral=True
                )
                return
            
            # Process the feedback
            server = await self.db.servers.find_one({"server_id": last_claim.get("server_id")})
            role_config = {}
            if server:
                member = self.bot.get_guild(server["server_id"]).get_member(interaction.user.id)
                if member:
                    role_config = await self.get_user_role_config(member, server)
            
            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
            trust_gain = 0.25 * trust_multiplier
            
            # Perfect rating bonus
            perfect_bonus = 0
            if rating == 5:
                config = await self.db.config.find_one({"_id": "bot_config"})
                perfect_bonus = config.get("point_rates", {}).get("perfect_rating_bonus", 1) if config else 1
            
            # Update user data
            await self.db.users.update_one(
                {"user_id": interaction.user.id},
                {
                    "$set": {
                        "last_claim.rating": rating,
                        "last_claim.feedback_text": feedback,
                        "last_claim.text_feedback_given": True,
                        "last_claim.text_feedback_time": datetime.now(timezone.utc)
                    },
                    "$inc": {
                        "trust_score": trust_gain,
                        "statistics.feedback_streak": 1,
                        "points": perfect_bonus,
                        "total_earned": perfect_bonus
                    }
                }
            )
            
            # Create response
            stars = "⭐" * rating
            embed = discord.Embed(
                title=f"✅ Quick Feedback Submitted!",
                color=discord.Color.green()
            )
            
            # Encouraging messages based on rating
            encouragement = {
                5: "🌟 Perfect! Thanks for the amazing feedback!",
                4: "👍 Great! Thanks for your honest review!",
                3: "👌 Thanks for letting us know! We'll work on improvements!",
                2: "⚠️ Thanks for reporting the issues! We'll investigate!",
                1: "❌ Sorry it didn't work! We'll check our stock!"
            }
            
            embed.description = encouragement.get(rating, "Thanks for your feedback!")
            
            embed.add_field(name="Your Rating", value=stars, inline=True)
            embed.add_field(name="Trust Gained", value=f"+{trust_gain:.2f}", inline=True)
            
            if perfect_bonus > 0:
                embed.add_field(name="🎁 Perfect Bonus!", value=f"+{perfect_bonus} points", inline=True)
            
            if has_screenshot:
                embed.add_field(
                    name="✅ Status",
                    value="**FEEDBACK COMPLETE!** All done! 🎉",
                    inline=False
                )
                # Mark as fully complete
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {"$set": {"last_claim.feedback_given": True}}
                )
            else:
                if server:
                    embed.add_field(
                        name="📸 Last Step",
                        value=f"Post a screenshot in <#{server['channels']['feedback']}> to complete!\n"
                              f"**Any screenshot showing {cookie_type} is fine!**",
                        inline=False
                    )
                embed.set_footer(text="Almost done! Just need a screenshot!")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log action
            if server:
                await self.log_action(
                    server["server_id"],
                    f"⭐ {interaction.user.mention} rated **{cookie_type}** cookie {stars} (Quick feedback)",
                    discord.Color.green()
                )
                
        except Exception as e:
            print(f"Error in quick feedback: {traceback.format_exc()}")
            await interaction.followup.send("❌ Error processing feedback!", ephemeral=True)
    
    async def process_feedback_submission(self, interaction: discord.Interaction, rating: int, feedback: str, cookie_type: str = None):
        """Process detailed feedback submission"""
        try:
            user_data = await self.db.users.find_one({"user_id": interaction.user.id})
            if not user_data or not user_data.get("last_claim"):
                await interaction.followup.send("❌ No recent cookie claim found!", ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            # Check what's already submitted
            has_text_feedback = last_claim.get("rating") is not None
            has_screenshot = last_claim.get("screenshot", False)
            
            if has_text_feedback and has_screenshot:
                await interaction.followup.send(
                    "✅ **Perfect!** You've already completed everything!\n"
                    f"• Rating: {'⭐' * last_claim.get('rating', 0)}\n"
                    f"• Screenshot: ✅\n"
                    f"You're all set! 🎉",
                    ephemeral=True
                )
                return
            
            if has_text_feedback:
                if has_screenshot:
                    await interaction.followup.send(
                        "✅ **All done!** Everything is already submitted!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"✅ **Rating already done!**\n"
                        f"📸 Just post a screenshot to complete!",
                        ephemeral=True
                    )
                return
            
            # Process NEW feedback
            server = await self.db.servers.find_one({"server_id": interaction.guild_id})
            role_config = await self.get_user_role_config(interaction.user, server) if server else {}
            
            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
            trust_gain = 0.25 * trust_multiplier
            
            # Perfect rating bonus
            config = await self.db.config.find_one({"_id": "bot_config"})
            perfect_bonus = 0
            if rating == 5 and config:
                perfect_bonus = config.get("point_rates", {}).get("perfect_rating_bonus", 1)
            
            # Update user data
            update_data = {
                "$set": {
                    "last_claim.rating": rating,
                    "last_claim.feedback_text": feedback,
                    "last_claim.text_feedback_given": True,
                    "last_claim.text_feedback_time": datetime.now(timezone.utc)
                },
                "$inc": {
                    "trust_score": trust_gain,
                    "statistics.feedback_streak": 1
                }
            }
            
            if perfect_bonus > 0:
                update_data["$inc"]["points"] = perfect_bonus
                update_data["$inc"]["total_earned"] = perfect_bonus
            
            await self.db.users.update_one(
                {"user_id": interaction.user.id},
                update_data
            )
            
            # Create encouraging response
            stars = "⭐" * rating
            embed = discord.Embed(
                title="✅ Feedback Received!",
                color=discord.Color.green()
            )
            
            if has_screenshot:
                embed.description = (
                    f"**🎉 PERFECT! All done!**\n\n"
                    f"✅ Rating: {stars}\n"
                    f"✅ Screenshot: Already posted\n\n"
                    f"**Thank you for completing everything!** 🎊"
                )
                # Mark as fully complete
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {"$set": {"last_claim.feedback_given": True}}
                )
            else:
                embed.description = (
                    f"**Great! Rating received: {stars}**\n\n"
                    f"📸 **Last step:** Post any screenshot of {last_claim['type']} in the feedback channel!"
                )
                embed.add_field(
                    name="💡 Easy Screenshot Tips",
                    value=f"• Any screenshot showing {last_claim['type']} is perfect!\n"
                          f"• Even the login page works!\n"
                          f"• Quick bonus: Post within 2 minutes for +0.5 points!",
                    inline=False
                )
            
            embed.add_field(name="Trust Gained", value=f"+{trust_gain:.2f}", inline=True)
            if perfect_bonus > 0:
                embed.add_field(name="🎁 Perfect Bonus!", value=f"+{perfect_bonus} points", inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log action
            await self.log_action(
                interaction.guild_id,
                f"📝 {interaction.user.mention} submitted feedback for **{last_claim['type']}** {stars}",
                discord.Color.green()
            )
            
            # Insert feedback record
            await self.db.feedback.insert_one({
                "user_id": interaction.user.id,
                "cookie_type": last_claim["type"],
                "file": last_claim["file"],
                "rating": rating,
                "feedback": feedback,
                "timestamp": datetime.now(timezone.utc),
                "server_id": interaction.guild_id,
                "has_screenshot": has_screenshot,
                "feedback_type": "complete" if has_screenshot else "text_only"
            })
            
        except Exception as e:
            print(f"Error in feedback submission: {traceback.format_exc()}")
            await interaction.followup.send("❌ Error submitting feedback!", ephemeral=True)
    
    @tasks.loop(minutes=5)
    async def send_feedback_reminders(self):
        """Send friendly reminders 10 and 5 minutes before deadline"""
        try:
            now = datetime.now(timezone.utc)
            
            # 10-minute reminder
            ten_min_window = now + timedelta(minutes=10)
            cursor_10 = self.db.users.find({
                "last_claim.feedback_given": False,
                "last_claim.feedback_deadline": {
                    "$gt": ten_min_window - timedelta(seconds=30),
                    "$lt": ten_min_window + timedelta(seconds=30)
                },
                "last_claim.reminder_10_sent": {"$ne": True}
            })
            
            async for user in cursor_10:
                asyncio.create_task(self.send_reminder(user, 10))
                await self.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {"last_claim.reminder_10_sent": True}}
                )
            
            # 5-minute urgent reminder
            five_min_window = now + timedelta(minutes=5)
            cursor_5 = self.db.users.find({
                "last_claim.feedback_given": False,
                "last_claim.feedback_deadline": {
                    "$gt": five_min_window - timedelta(seconds=30),
                    "$lt": five_min_window + timedelta(seconds=30)
                },
                "last_claim.reminder_5_sent": {"$ne": True}
            })
            
            async for user in cursor_5:
                asyncio.create_task(self.send_reminder(user, 5))
                await self.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {"last_claim.reminder_5_sent": True}}
                )
                
        except Exception as e:
            print(f"Error in reminder system: {e}")
    
    async def send_reminder(self, user_data: dict, minutes_left: int):
        """Send a friendly reminder with quick action buttons"""
        try:
            discord_user = self.bot.get_user(user_data["user_id"])
            if not discord_user:
                return
            
            last_claim = user_data["last_claim"]
            has_text = last_claim.get("rating") is not None
            has_screenshot = last_claim.get("screenshot", False)
            cookie_type = last_claim.get("type", "unknown")
            
            if minutes_left == 10:
                # Friendly 10-minute reminder
                embed = discord.Embed(
                    title=f"🍪 Quick Reminder - {minutes_left} minutes left!",
                    color=discord.Color.blue()
                )
                
                if not has_text and not has_screenshot:
                    embed.description = (
                        f"Hey! Don't forget to submit feedback for your **{cookie_type}** cookie!\n\n"
                        f"**Super easy - just click a button below!** 👇"
                    )
                    view = QuickFeedbackView(cookie_type, user_data["user_id"], self)
                    await discord_user.send(embed=embed, view=view)
                elif not has_screenshot:
                    embed.description = (
                        f"Almost done with your **{cookie_type}** feedback!\n"
                        f"✅ Rating submitted\n"
                        f"📸 Just need a quick screenshot!"
                    )
                    await discord_user.send(embed=embed)
                elif not has_text:
                    embed.description = (
                        f"Almost done with your **{cookie_type}** feedback!\n"
                        f"✅ Screenshot posted\n"
                        f"⭐ Just click a rating below!"
                    )
                    view = QuickFeedbackView(cookie_type, user_data["user_id"], self)
                    await discord_user.send(embed=embed, view=view)
                    
            elif minutes_left == 5:
                # Urgent but still friendly 5-minute reminder
                embed = discord.Embed(
                    title=f"⏰ Last Call - {minutes_left} minutes!",
                    color=discord.Color.orange()
                )
                
                if not has_text and not has_screenshot:
                    embed.description = (
                        f"**Quick! Your {cookie_type} cookie needs feedback!**\n\n"
                        f"Just click one button below - takes 1 second! ⚡"
                    )
                    view = QuickFeedbackView(cookie_type, user_data["user_id"], self)
                    await discord_user.send(embed=embed, view=view)
                elif not has_screenshot:
                    embed.description = (
                        f"**Last step for {cookie_type} feedback!**\n"
                        f"📸 Post ANY screenshot - even login page works!"
                    )
                    await discord_user.send(embed=embed)
                elif not has_text:
                    embed.description = (
                        f"**One click to complete {cookie_type} feedback!**\n"
                        f"⭐ Just pick a rating below!"
                    )
                    view = QuickFeedbackView(cookie_type, user_data["user_id"], self)
                    await discord_user.send(embed=embed, view=view)
                    
        except Exception as e:
            print(f"Error sending reminder: {e}")
    
    @tasks.loop(minutes=1)
    async def check_feedback_deadlines(self):
        """Check for missed deadlines with 2-minute grace period"""
        try:
            now = datetime.now(timezone.utc)
            
            # Add 2-minute grace period - be lenient!
            grace_period_ago = now - timedelta(minutes=2)
            
            # Find users who haven't given feedback
            cursor = self.db.users.find({
                "last_claim.feedback_given": False,
                "last_claim.feedback_deadline": {"$lt": grace_period_ago},
                "last_claim.text_feedback_given": {"$ne": True},
                "last_claim.screenshot": {"$ne": True},
                "blacklisted": False
            })
            
            async for user in cursor:
                # Give one last chance
                discord_user = self.bot.get_user(user["user_id"])
                if discord_user:
                    try:
                        # Send last chance message with quick buttons
                        embed = discord.Embed(
                            title="⚠️ LAST CHANCE - Feedback Overdue!",
                            description=(
                                f"Your {user['last_claim']['type']} cookie feedback is overdue!\n\n"
                                f"**Click any button NOW to avoid blacklist!**"
                            ),
                            color=discord.Color.red()
                        )
                        view = QuickFeedbackView(user['last_claim']['type'], user["user_id"], self)
                        message = await discord_user.send(embed=embed, view=view)
                        
                        # Wait 30 seconds for response
                        await asyncio.sleep(30)
                        
                        # Check again if feedback was given
                        updated_user = await self.db.users.find_one({"user_id": user["user_id"]})
                        if updated_user["last_claim"].get("text_feedback_given") or updated_user["last_claim"].get("screenshot"):
                            # They responded! Don't blacklist
                            continue
                            
                    except:
                        pass
                
                # If still no feedback after grace period and last chance, then blacklist
                last_claim = user.get("last_claim")
                if last_claim:
                    server = await self.db.servers.find_one({"server_id": last_claim.get("server_id")})
                    blacklist_duration = 30
                    if server:
                        blacklist_duration = server.get("settings", {}).get("feedback_blacklist_days", 30)
                    
                    await self.db.users.update_one(
                        {"user_id": user["user_id"]},
                        {
                            "$set": {
                                "blacklisted": True,
                                "blacklist_expires": now + timedelta(days=blacklist_duration),
                                "blacklist_reason": "No feedback provided (after grace period)",
                                "statistics.feedback_streak": 0,
                                "trust_score": max(0, user.get("trust_score", 50) - 5)
                            }
                        }
                    )
                    
                    if discord_user:
                        try:
                            embed = discord.Embed(
                                title="😔 Blacklisted - No Feedback",
                                description=(
                                    f"You didn't provide feedback for your {last_claim['type']} cookie.\n\n"
                                    f"**Duration:** {blacklist_duration} days\n"
                                    f"**Expires:** <t:{int((now + timedelta(days=blacklist_duration)).timestamp())}:R>\n\n"
                                    f"💡 **Tip:** Next time, just click one button for instant feedback!"
                                ),
                                color=discord.Color.red()
                            )
                            await discord_user.send(embed=embed)
                        except:
                            pass
                    
                    if last_claim.get("server_id"):
                        await self.log_action(
                            last_claim["server_id"],
                            f"🚫 <@{user['user_id']}> blacklisted for {blacklist_duration} days (no feedback after grace period)",
                            discord.Color.red()
                        )
                        
        except Exception as e:
            print(f"Error in deadline check: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle screenshot submissions"""
        if message.author.bot:
            return
            
        if message.attachments and message.channel.type == discord.ChannelType.text:
            try:
                server = await self.db.servers.find_one({"server_id": message.guild.id})
                if server and message.channel.id == server["channels"].get("feedback"):
                    user_data = await self.db.users.find_one({"user_id": message.author.id})
                    if user_data and user_data.get("last_claim"):
                        last_claim = user_data["last_claim"]
                        
                        # Check what's already submitted
                        has_text_feedback = last_claim.get("rating") is not None
                        has_screenshot = last_claim.get("screenshot", False)
                        
                        if has_screenshot:
                            return  # Already has screenshot
                        
                        # Check for image
                        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                        has_image = any(att.filename.lower().endswith(ext.lower()) 
                                      for att in message.attachments for ext in image_extensions)
                        
                        if has_image:
                            cookie_type = last_claim.get("type", "unknown")
                            
                            # Calculate bonuses
                            role_config = await self.get_user_role_config(message.author, server)
                            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
                            
                            config = await self.db.config.find_one({"_id": "bot_config"})
                            feedback_bonus = config.get("point_rates", {}).get("feedback_bonus", 1) if config else 1
                            
                            screenshot_trust = 0.25 * trust_multiplier
                            
                            # Quick feedback bonus
                            quick_bonus = 0
                            if has_text_feedback:
                                text_time = last_claim.get("text_feedback_time")
                                if text_time:
                                    if isinstance(text_time, datetime) and text_time.tzinfo is None:
                                        text_time = text_time.replace(tzinfo=timezone.utc)
                                    if (datetime.now(timezone.utc) - text_time).total_seconds() <= 120:
                                        quick_bonus = 0.5
                            
                            # Update database
                            update_data = {
                                "$set": {
                                    "last_claim.screenshot": True,
                                    "last_claim.screenshot_time": datetime.now(timezone.utc),
                                    "last_claim.screenshot_url": message.attachments[0].url
                                },
                                "$inc": {
                                    "trust_score": screenshot_trust,
                                    "points": feedback_bonus + quick_bonus,
                                    "total_earned": feedback_bonus + quick_bonus
                                }
                            }
                            
                            if has_text_feedback:
                                update_data["$set"]["last_claim.feedback_given"] = True
                            else:
                                update_data["$inc"]["statistics.feedback_streak"] = 1
                            
                            await self.db.users.update_one(
                                {"user_id": message.author.id},
                                update_data
                            )
                            
                            # Send encouraging response
                            if has_text_feedback:
                                # Both complete!
                                embed = discord.Embed(
                                    title="🎉 **PERFECT! All Done!**",
                                    color=discord.Color.green()
                                )
                                
                                rating = last_claim.get("rating", 0)
                                stars = "⭐" * rating
                                
                                embed.description = (
                                    f"**Awesome! Feedback complete for {cookie_type}!**\n\n"
                                    f"✅ Rating: {stars}\n"
                                    f"✅ Screenshot: Just received!\n\n"
                                    f"**Thank you! No blacklist risk!** 🛡️"
                                )
                                
                                if quick_bonus > 0:
                                    embed.add_field(
                                        name="⚡ Speed Bonus!",
                                        value="+0.5 points for quick completion!",
                                        inline=False
                                    )
                                
                                embed.add_field(name="Points Earned", value=f"+{feedback_bonus + quick_bonus}", inline=True)
                                embed.add_field(name="Trust Gained", value=f"+{0.5 * trust_multiplier:.2f}", inline=True)
                                
                                await message.add_reaction("✅")
                                await message.add_reaction("🎉")
                                if quick_bonus > 0:
                                    await message.add_reaction("⚡")
                                    
                            else:
                                # Screenshot first, need rating
                                embed = discord.Embed(
                                    title="📸 Screenshot Received!",
                                    color=discord.Color.gold()
                                )
                                
                                embed.description = (
                                    f"**Great! Screenshot for {cookie_type} saved!**\n\n"
                                    f"✅ Screenshot: Done\n"
                                    f"⭐ **Last step:** Rate your experience!\n\n"
                                    f"**Click a button below for instant rating!**"
                                )
                                
                                embed.add_field(name="Trust Gained", value=f"+{screenshot_trust:.2f}", inline=True)
                                embed.add_field(name="Points Earned", value=f"+{feedback_bonus}", inline=True)
                                
                                # Send with quick rating buttons
                                view = QuickFeedbackView(cookie_type, message.author.id, self)
                                
                                await message.add_reaction("📸")
                                await message.add_reaction("👍")
                                
                                dm_msg = await message.author.send(embed=embed, view=view)
                            
                            try:
                                if not has_text_feedback:
                                    # If no DM, reply in channel
                                    view = QuickFeedbackView(cookie_type, message.author.id, self)
                                    await message.reply(embed=embed, view=view, delete_after=60)
                                else:
                                    await message.author.send(embed=embed)
                            except discord.Forbidden:
                                pass
                                
            except Exception as e:
                print(f"Error processing screenshot: {traceback.format_exc()}")
    
    @commands.hybrid_command(name="feedback", description="Submit feedback easily")
    async def feedback(self, ctx):
        try:
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.response.defer(ephemeral=True)
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            user_data = await self.db.users.find_one({"user_id": ctx.author.id})
            if not user_data or not user_data.get("last_claim"):
                embed = discord.Embed(
                    title="❌ No Cookie to Review",
                    description="You haven't claimed any cookies recently!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            # Check if already complete
            if last_claim.get("feedback_given") and last_claim.get("screenshot"):
                embed = discord.Embed(
                    title="✅ Already Complete!",
                    description=f"You've already submitted everything for your {last_claim['type']} cookie!",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            deadline = last_claim["feedback_deadline"]
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            
            # Be lenient - allow even if slightly past deadline
            if datetime.now(timezone.utc) > deadline + timedelta(minutes=5):
                embed = discord.Embed(
                    title="⏰ Deadline Passed",
                    description="The feedback deadline has passed. Try to be quicker next time!",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            # Show current status with quick buttons
            embed = discord.Embed(
                title=f"📝 Quick Feedback for {last_claim['type'].title()}",
                description="**Super easy! Just click a button below!**",
                color=discord.Color.blue()
            )
            
            # Show status
            has_text = last_claim.get("rating") is not None
            has_screenshot = last_claim.get("screenshot", False)
            
            status_text = []
            if has_text:
                status_text.append(f"✅ Rating: {'⭐' * last_claim.get('rating', 0)}")
            else:
                status_text.append("❌ Rating: Not submitted")
                
            if has_screenshot:
                status_text.append("✅ Screenshot: Submitted")
            else:
                status_text.append("❌ Screenshot: Not submitted")
            
            embed.add_field(
                name="📊 Current Status",
                value="\n".join(status_text),
                inline=False
            )
            
            embed.add_field(
                name="⏰ Deadline",
                value=f"<t:{int(deadline.timestamp())}:R>",
                inline=True
            )
            
            # Add quick feedback view
            view = QuickFeedbackView(last_claim["type"], ctx.author.id, self)
            
            await ctx.send(embed=embed, view=view, ephemeral=True)
                
        except Exception as e:
            print(f"Error in feedback command: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @send_feedback_reminders.before_loop
    async def before_send_reminders(self):
        await self.bot.wait_until_ready()
    
    @check_feedback_deadlines.before_loop
    async def before_check_deadlines(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))