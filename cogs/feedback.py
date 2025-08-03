import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone
import traceback
from typing import Optional
import asyncio

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
                
            # Defer the response immediately to avoid timeout
            await interaction.response.defer(ephemeral=True)
            
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
        self.FeedbackModal = FeedbackModal
        
    async def cog_unload(self):
        self.check_feedback_deadlines.cancel()
        
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
    
    async def process_feedback_submission(self, interaction: discord.Interaction, rating: int, feedback: str, cookie_type: str = None):
        try:
            # The interaction is already deferred, so we can take our time with database operations
            
            user_data = await self.db.users.find_one({"user_id": interaction.user.id})
            if not user_data or not user_data.get("last_claim"):
                await interaction.followup.send("❌ No recent cookie claim found!", ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            # Check if feedback is already complete (both text and photo)
            if last_claim.get("feedback_given") and last_claim.get("screenshot"):
                await interaction.followup.send("✅ You already submitted complete feedback!", ephemeral=True)
                return
            
            # Check if text feedback already submitted
            if last_claim.get("rating"):
                await interaction.followup.send("✅ You already submitted text feedback! Post a screenshot for bonus points.", ephemeral=True)
                return
            
            if cookie_type and last_claim.get("type") != cookie_type:
                await interaction.followup.send("❌ This feedback doesn't match your last claim!", ephemeral=True)
                return
            
            # Get user's streak and role config
            current_streak = user_data.get("statistics", {}).get("feedback_streak", 0)
            
            server = await self.db.servers.find_one({"server_id": interaction.guild_id})
            role_config = await self.get_user_role_config(interaction.user, server) if server else {}
            
            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
            base_trust_gain = 0.25  # 0.25 for text feedback
            
            # Handle perfect rating bonus
            config = await self.db.config.find_one({"_id": "bot_config"})
            perfect_rating_bonus = 0
            if rating == 5 and config:
                perfect_rating_bonus = config.get("point_rates", {}).get("perfect_rating_bonus", 0)
                if perfect_rating_bonus > 0:
                    await self.db.users.update_one(
                        {"user_id": interaction.user.id},
                        {"$inc": {"statistics.perfect_ratings": 1}}
                    )
            
            # Apply trust gain for text feedback
            trust_gain = base_trust_gain * trust_multiplier
            
            # Update user data with text feedback
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
            
            # Add perfect rating bonus if applicable
            if perfect_rating_bonus > 0:
                update_data["$inc"]["points"] = perfect_rating_bonus
                update_data["$inc"]["total_earned"] = perfect_rating_bonus
            
            await self.db.users.update_one(
                {"user_id": interaction.user.id},
                update_data
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
                "has_screenshot": False,  # Will be updated when photo is posted
                "trust_multiplier_applied": trust_multiplier,
                "feedback_type": "text_only"
            })
            
            # Create response embed
            stars = "⭐" * rating
            embed = discord.Embed(
                title="✅ Text Feedback Submitted!",
                description=f"Thank you for rating the **{last_claim['type']}** cookie!",
                color=discord.Color.green()
            )
            embed.add_field(name="Rating", value=stars, inline=True)
            embed.add_field(name="Trust Score", value=f"+{trust_gain:.2f} points", inline=True)
            embed.add_field(name="Streak", value=f"{current_streak + 1} feedback(s)", inline=True)
            
            if perfect_rating_bonus > 0:
                embed.add_field(
                    name="🎉 Perfect Rating Bonus!",
                    value=f"+{perfect_rating_bonus} points",
                    inline=True
                )
            
            if role_config and trust_multiplier > 1.0:
                embed.add_field(
                    name="🎭 Role Bonus",
                    value=f"×{trust_multiplier} trust multiplier applied!",
                    inline=False
                )
            
            # Always remind about screenshot
            if server and server.get("channels", {}).get("feedback"):
                embed.add_field(
                    name="📸 Next Step: Screenshot Required!",
                    value=f"Post your screenshot in <#{server['channels']['feedback']}> to:\n"
                          f"• Complete your feedback\n"
                          f"• Get +{0.25 * trust_multiplier:.2f} more trust\n"
                          f"• Earn bonus points\n"
                          f"• Avoid blacklist\n"
                          f"**⚡ Quick bonus: +0.5 points if posted within 2 minutes!**",
                    inline=False
                )
            
            embed.set_footer(text="⚠️ Screenshot still required to avoid blacklist!")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log the text feedback
            stars = "⭐" * rating
            await self.log_action(
                interaction.guild_id,
                f"📝 {interaction.user.mention} submitted text feedback for **{last_claim['type']}** cookie {stars} - \"{feedback[:50]}{'...' if len(feedback) > 50 else ''}\" (Photo pending)",
                discord.Color.gold()
            )
            
        except discord.NotFound:
            print(f"Interaction expired for user {interaction.user.id}")
            try:
                await interaction.user.send(
                    "⚠️ Your feedback submission took too long to process. "
                    "Please try again using the `/feedback` command!"
                )
            except:
                pass
        except Exception as e:
            print(f"Error in process_feedback_submission: {traceback.format_exc()}")
            try:
                await interaction.followup.send("❌ Error submitting feedback!", ephemeral=True)
            except:
                pass
    
    @tasks.loop(minutes=1)
    async def check_feedback_deadlines(self):
        try:
            now = datetime.now(timezone.utc)
            
            # Find users who haven't given ANY feedback (text or photo)
            cursor = self.db.users.find({
                "last_claim.feedback_given": False,
                "last_claim.feedback_deadline": {"$lt": now},
                "last_claim.text_feedback_given": {"$ne": True},  # No text feedback
                "last_claim.screenshot": {"$ne": True},  # No screenshot
                "blacklisted": False
            })
            
            batch = []
            async for user in cursor:
                batch.append(user)
                if len(batch) >= 10:
                    await self._process_deadline_batch(batch, now)
                    batch = []
            
            if batch:
                await self._process_deadline_batch(batch, now)
                
        except Exception as e:
            print(f"Error in feedback check: {e}")
    
    async def _process_deadline_batch(self, users, now):
        for user in users:
            try:
                last_claim = user.get("last_claim")
                if last_claim and last_claim.get("feedback_deadline"):
                    server = await self.db.servers.find_one({"server_id": last_claim.get("server_id")})
                    settings = server.get("settings", {}) if server else {}
                    
                    blacklist_duration = settings.get("feedback_blacklist_days", 30)
                    
                    current_trust = user.get("trust_score", 50)
                    new_trust = max(0, current_trust - 5)  # Bigger penalty for no feedback
                    
                    await self.db.users.update_one(
                        {"user_id": user["user_id"]},
                        {
                            "$set": {
                                "blacklisted": True,
                                "blacklist_expires": now + timedelta(days=blacklist_duration),
                                "blacklist_reason": "No feedback provided",
                                "statistics.feedback_streak": 0,
                                "trust_score": new_trust
                            }
                        }
                    )
                    
                    guild_id = last_claim.get("server_id")
                    if guild_id:
                        await self.log_action(
                            guild_id,
                            f"🚫 <@{user['user_id']}> blacklisted for {blacklist_duration} days for not providing feedback",
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
                                embed.add_field(name="Duration", value=f"{blacklist_duration} days", inline=True)
                                embed.add_field(name="Expires", value=f"<t:{int((now + timedelta(days=blacklist_duration)).timestamp())}:R>", inline=True)
                                embed.add_field(name="Trust Lost", value=f"-5 points (now {new_trust}/100)", inline=True)
                                await user_obj.send(embed=embed)
                        except:
                            pass
            except Exception as e:
                print(f"Error processing user {user.get('user_id')}: {e}")
    
    @commands.hybrid_command(name="feedback", description="Submit feedback with interactive form")
    async def feedback(self, ctx):
        try:
            # Defer the response immediately if it's an interaction
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.response.defer(ephemeral=True)
            
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
            
            # Check if complete feedback already given
            if last_claim.get("feedback_given") and last_claim.get("screenshot"):
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
            
            embed = discord.Embed(
                title="📸 Submit Feedback",
                description=f"Click the button below to submit feedback for your **{last_claim['type']}** cookie!",
                color=discord.Color.blue()
            )
            
            # Show current status
            status_text = []
            if last_claim.get("rating"):
                status_text.append("✅ Text feedback submitted")
            else:
                status_text.append("❌ Text feedback needed")
                
            if last_claim.get("screenshot"):
                status_text.append("✅ Screenshot submitted")
            else:
                status_text.append("❌ Screenshot needed")
            
            embed.add_field(
                name="📊 Current Status",
                value="\n".join(status_text),
                inline=False
            )
            
            embed.add_field(
                name="⏰ Deadline",
                value=f"<t:{int(deadline.timestamp())}:R>",
                inline=False
            )
            
            # Add quick feedback bonus info
            embed.add_field(
                name="⚡ Quick Feedback Bonus",
                value="Submit both text and screenshot within **2 minutes** for +0.5 bonus points!",
                inline=False
            )
            
            role_config = await self.get_user_role_config(ctx.author, server)
            if role_config and role_config.get("trust_multiplier", 1.0) > 1.0:
                embed.add_field(
                    name="🎭 Role Benefit",
                    value=f"Your {role_config.get('name', 'role')} gives ×{role_config['trust_multiplier']} trust bonus!",
                    inline=False
                )
            
            button = discord.ui.Button(
                label="Submit Feedback",
                style=discord.ButtonStyle.success,
                emoji="📸"
            )
            
            modal = FeedbackModal(last_claim["type"])
            
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
                        
                        # Check if screenshot already submitted
                        if last_claim.get("screenshot"):
                            return
                        
                        # Verify it's an image
                        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                        has_image = any(att.filename.lower().endswith(ext.lower()) for att in message.attachments for ext in image_extensions)
                        
                        if has_image:
                            cookie_type = last_claim.get("type", "unknown")
                            
                            # Get role config for trust multiplier
                            role_config = await self.get_user_role_config(message.author, server)
                            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
                            
                            # Get feedback bonus points from config
                            config = await self.db.config.find_one({"_id": "bot_config"})
                            feedback_bonus_points = config.get("point_rates", {}).get("feedback_bonus", 1) if config else 1
                            
                            # Calculate trust gain for screenshot
                            screenshot_trust = 0.25 * trust_multiplier
                            
                            # Check if text feedback was already given
                            has_text_feedback = last_claim.get("rating") is not None
                            
                            if has_text_feedback:
                                # Complete feedback (text + photo)
                                # Check if feedback was submitted within 2 minutes
                                # Check if feedback was submitted within 2 minutes
                                quick_feedback_bonus = 0
                                text_feedback_time = last_claim.get("text_feedback_time")
                                if text_feedback_time:
                                    # Ensure text_feedback_time is timezone-aware
                                    if isinstance(text_feedback_time, datetime):
                                        if text_feedback_time.tzinfo is None:
                                            text_feedback_time = text_feedback_time.replace(tzinfo=timezone.utc)
                                    time_diff = (datetime.now(timezone.utc) - text_feedback_time).total_seconds()
                                    if time_diff <= 120:  # Within 2 minutes
                                        quick_feedback_bonus = 0.5
                                
                                await self.db.users.update_one(
                                    {"user_id": message.author.id},
                                    {
                                        "$set": {
                                            "last_claim.feedback_given": True,
                                            "last_claim.screenshot": True,
                                            "last_claim.screenshot_time": datetime.now(timezone.utc),
                                            "last_claim.screenshot_url": message.attachments[0].url
                                        },
                                        "$inc": {
                                            "trust_score": screenshot_trust,
                                            "points": feedback_bonus_points + quick_feedback_bonus,
                                            "total_earned": feedback_bonus_points + quick_feedback_bonus
                                        }
                                    }
                                )
                                
                                # Update existing feedback record
                                await self.db.feedback.update_one(
                                    {
                                        "user_id": message.author.id,
                                        "cookie_type": cookie_type,
                                        "timestamp": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=30)}
                                    },
                                    {
                                        "$set": {
                                            "has_screenshot": True,
                                            "screenshot_url": message.attachments[0].url,
                                            "feedback_type": "complete",
                                            "quick_feedback_bonus": quick_feedback_bonus > 0
                                        }
                                    }
                                )
                                
                                embed_title = "🎉 Feedback Complete!"
                                embed_description = "Both text and screenshot submitted!"
                                if quick_feedback_bonus > 0:
                                    embed_description += "\n⚡ Quick feedback bonus earned!"
                                total_trust = 0.5 * trust_multiplier  # 0.25 + 0.25
                                
                                # Log complete feedback
                                stars = "⭐" * last_claim.get("rating", 0)
                                feedback_text = last_claim.get('feedback_text', '')[:50]
                                if len(last_claim.get('feedback_text', '')) > 50:
                                    feedback_text += "..."
                                
                                log_message = f"🎉 {message.author.mention} completed feedback for **{cookie_type}** cookie with screenshot {stars} - \"{feedback_text}\""
                                if quick_feedback_bonus > 0:
                                    log_message += " ⚡ +0.5 quick bonus!"
                                
                                await self.log_action(
                                    message.guild.id,
                                    log_message,
                                    discord.Color.green()
                                )
                            else:
                                # Only screenshot (no text yet)
                                await self.db.users.update_one(
                                    {"user_id": message.author.id},
                                    {
                                        "$set": {
                                            "last_claim.screenshot": True,
                                            "last_claim.screenshot_time": datetime.now(timezone.utc),
                                            "last_claim.screenshot_url": message.attachments[0].url
                                        },
                                        "$inc": {
                                            "trust_score": screenshot_trust,
                                            "statistics.feedback_streak": 1,
                                            "points": feedback_bonus_points,
                                            "total_earned": feedback_bonus_points
                                        }
                                    }
                                )
                                
                                # Create new feedback record for screenshot only
                                await self.db.feedback.insert_one({
                                    "user_id": message.author.id,
                                    "cookie_type": cookie_type,
                                    "file": last_claim["file"],
                                    "rating": None,
                                    "feedback": None,
                                    "timestamp": datetime.now(timezone.utc),
                                    "server_id": message.guild.id,
                                    "has_screenshot": True,
                                    "screenshot_url": message.attachments[0].url,
                                    "trust_multiplier_applied": trust_multiplier,
                                    "feedback_type": "screenshot_only"
                                })
                                
                                embed_title = "📸 Screenshot Received!"
                                embed_description = "Photo submitted! Use `/feedback` for text review.\n⚡ Submit text within 2 minutes for +0.5 bonus!"
                                total_trust = screenshot_trust
                                quick_feedback_bonus = 0
                                
                                await self.log_action(
                                    message.guild.id,
                                    f"📸 {message.author.mention} submitted screenshot for **{cookie_type}** cookie (Text feedback pending)",
                                    discord.Color.gold()
                                )
                            
                            # Add reactions
                            await message.add_reaction("✅")
                            await message.add_reaction("📸")
                            if has_text_feedback:
                                await message.add_reaction("🎉")
                                if quick_feedback_bonus > 0:
                                    await message.add_reaction("⚡")
                            
                            try:
                                embed = discord.Embed(
                                    title=embed_title,
                                    description=embed_description,
                                    color=discord.Color.green()
                                )
                                
                                embed.add_field(
                                    name="🏆 Trust Score", 
                                    value=f"+{total_trust:.2f} points",
                                    inline=True
                                )
                                embed.add_field(
                                    name="💰 Bonus Points",
                                    value=f"+{feedback_bonus_points + quick_feedback_bonus}",
                                    inline=True
                                )
                                embed.add_field(
                                    name="🍪 Cookie Type",
                                    value=cookie_type.title(),
                                    inline=True
                                )
                                
                                if quick_feedback_bonus > 0:
                                    embed.add_field(
                                        name="⚡ Quick Bonus",
                                        value="+0.5 points for fast feedback!",
                                        inline=False
                                    )
                                
                                if role_config and trust_multiplier > 1.0:
                                    embed.add_field(
                                        name="🎭 Role Bonus",
                                        value=f"×{trust_multiplier} trust from {role_config.get('name', 'your role')}!",
                                        inline=False
                                    )
                                
                                if not has_text_feedback:
                                    embed.add_field(
                                        name="💡 Next Step",
                                        value="Use `/feedback` to add a text review for more trust points!\n⚡ Submit within 2 minutes for +0.5 bonus!",
                                        inline=False
                                    )
                                else:
                                    embed.add_field(
                                        name="✅ Status",
                                        value="Feedback complete! Thank you!",
                                        inline=False
                                    )
                                
                                await message.author.send(embed=embed)
                            except discord.Forbidden:
                                pass
                                
            except discord.HTTPException:
                pass
            except Exception as e:
                print(f"Error processing feedback attachment: {traceback.format_exc()}")

    @check_feedback_deadlines.before_loop
    async def before_check_feedback_deadlines(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))