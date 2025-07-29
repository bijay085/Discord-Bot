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
            user_data = await self.db.users.find_one({"user_id": interaction.user.id})
            if not user_data or not user_data.get("last_claim"):
                await interaction.response.send_message("❌ No recent cookie claim found!", ephemeral=True)
                return
            
            last_claim = user_data["last_claim"]
            
            if last_claim.get("feedback_given") and last_claim.get("rating"):
                await interaction.response.send_message("✅ You already submitted complete feedback!", ephemeral=True)
                return
            
            if last_claim.get("rating"):
                await interaction.response.send_message("✅ You already submitted text feedback! Post a screenshot for bonus points.", ephemeral=True)
                return
            
            if cookie_type and last_claim.get("type") != cookie_type:
                await interaction.response.send_message("❌ This feedback doesn't match your last claim!", ephemeral=True)
                return
            
            current_streak = user_data.get("statistics", {}).get("feedback_streak", 0)
            
            server = await self.db.servers.find_one({"server_id": interaction.guild_id})
            role_config = await self.get_user_role_config(interaction.user, server) if server else {}
            
            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
            base_trust_gain = 0.25
            
            if rating == 5:
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {"$inc": {"statistics.perfect_ratings": 1}}
                )
                
                config = await self.db.config.find_one({"_id": "bot_config"})
                if config and config.get("point_rates", {}).get("perfect_rating_bonus", 0) > 0:
                    bonus_points = config["point_rates"]["perfect_rating_bonus"]
                    await self.db.users.update_one(
                        {"user_id": interaction.user.id},
                        {"$inc": {"points": bonus_points}}
                    )
            
            if last_claim.get("screenshot"):
                trust_gain = base_trust_gain * trust_multiplier
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {
                        "$set": {
                            "last_claim.feedback_given": True,
                            "last_claim.rating": rating,
                            "last_claim.feedback_text": feedback
                        },
                        "$inc": {
                            "trust_score": trust_gain
                        }
                    }
                )
                trust_text = f"+{trust_gain:.2f} points (Total: {0.5 * trust_multiplier + trust_gain:.2f})"
                is_complete = True
                
                stars = "⭐" * rating
                await self.log_action(
                    interaction.guild_id,
                    f"📝 {interaction.user.mention} added text feedback for **{last_claim['type']}** cookie {stars} - \"{feedback[:50]}{'...' if len(feedback) > 50 else ''}\"",
                    discord.Color.green()
                )
            else:
                trust_gain = base_trust_gain * trust_multiplier
                await self.db.users.update_one(
                    {"user_id": interaction.user.id},
                    {
                        "$set": {
                            "last_claim.feedback_given": False,
                            "last_claim.rating": rating,
                            "last_claim.feedback_text": feedback,
                            "last_claim.text_feedback_only": True
                        },
                        "$inc": {
                            "trust_score": trust_gain,
                            "statistics.feedback_streak": 1
                        }
                    }
                )
                trust_text = f"+{trust_gain:.2f} points"
                is_complete = False
                
                stars = "⭐" * rating
                await self.log_action(
                    interaction.guild_id,
                    f"📝 {interaction.user.mention} submitted text feedback for **{last_claim['type']}** cookie {stars} - \"{feedback[:50]}{'...' if len(feedback) > 50 else ''}\" (Photo pending)",
                    discord.Color.gold()
                )
            
            await self.db.feedback.insert_one({
                "user_id": interaction.user.id,
                "cookie_type": last_claim["type"],
                "file": last_claim["file"],
                "rating": rating,
                "feedback": feedback,
                "timestamp": datetime.now(timezone.utc),
                "server_id": interaction.guild_id,
                "has_screenshot": last_claim.get("screenshot", False),
                "trust_multiplier_applied": trust_multiplier
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
            
            if role_config and trust_multiplier > 1.0:
                embed.add_field(
                    name="🎭 Role Bonus",
                    value=f"×{trust_multiplier} trust multiplier applied!",
                    inline=False
                )
            
            if not is_complete:
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
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Error submitting feedback!", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Error submitting feedback!", ephemeral=True)
            except:
                pass
    
    @tasks.loop(minutes=1)
    async def check_feedback_deadlines(self):
        try:
            now = datetime.now(timezone.utc)
            
            cursor = self.db.users.find({
                "last_claim.feedback_given": False,
                "last_claim.feedback_deadline": {"$lt": now},
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
                    new_trust = max(0, current_trust - 1)
                    
                    await self.db.users.update_one(
                        {"user_id": user["user_id"]},
                        {
                            "$set": {
                                "blacklisted": True,
                                "blacklist_expires": now + timedelta(days=blacklist_duration),
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
                        
                        if last_claim.get("screenshot"):
                            return
                        
                        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                        has_image = any(att.filename.lower().endswith(ext.lower()) for att in message.attachments for ext in image_extensions)
                        
                        if has_image:
                            cookie_type = last_claim.get("type", "unknown")
                            
                            role_config = await self.get_user_role_config(message.author, server)
                            trust_multiplier = role_config.get("trust_multiplier", 1.0) if role_config else 1.0
                            
                            config = await self.db.config.find_one({"_id": "bot_config"})
                            feedback_bonus_points = config.get("point_rates", {}).get("feedback_bonus", 1) if config else 1
                            
                            if last_claim.get("text_feedback_only"):
                                bonus = 0.5 * trust_multiplier
                                embed_title = "🎉 Feedback Complete!"
                                trust_text = f"+{bonus:.2f} points (Total: {0.75 * trust_multiplier:.2f})"
                                is_complete = True
                                
                                await self.db.users.update_one(
                                    {"user_id": message.author.id},
                                    {
                                        "$set": {
                                            "last_claim.feedback_given": True,
                                            "last_claim.screenshot": True
                                        },
                                        "$inc": {
                                            "trust_score": bonus,
                                            "points": feedback_bonus_points
                                        }
                                    }
                                )
                                
                                stars = "⭐" * last_claim.get("rating", 0) if last_claim.get("rating") else ""
                                feedback_text = f" - \"{last_claim.get('feedback_text', '')[:50]}{'...' if len(last_claim.get('feedback_text', '')) > 50 else ''}\"" if last_claim.get('feedback_text') else ""
                                
                                await self.log_action(
                                    message.guild.id,
                                    f"🎉 {message.author.mention} completed feedback for **{cookie_type}** cookie with screenshot {stars}{feedback_text}",
                                    discord.Color.green()
                                )
                            else:
                                bonus = 0.5 * trust_multiplier
                                embed_title = "📸 Screenshot Received!"
                                trust_text = f"+{bonus:.2f} points"
                                is_complete = False
                                
                                await self.db.users.update_one(
                                    {"user_id": message.author.id},
                                    {
                                        "$set": {
                                            "last_claim.screenshot": True
                                        },
                                        "$inc": {
                                            "trust_score": bonus,
                                            "statistics.feedback_streak": 1,
                                            "points": feedback_bonus_points
                                        }
                                    }
                                )
                                
                                await self.log_action(
                                    message.guild.id,
                                    f"📸 {message.author.mention} submitted screenshot for **{cookie_type}** cookie (Text feedback pending)",
                                    discord.Color.gold()
                                )
                            
                            await message.add_reaction("✅")
                            await message.add_reaction("📸")
                            
                            try:
                                embed = discord.Embed(
                                    title=embed_title,
                                    description=f"Thank you for the screenshot!",
                                    color=discord.Color.green()
                                )
                                embed.add_field(name="Trust Score", value=trust_text, inline=True)
                                embed.add_field(name="Cookie Type", value=cookie_type.title(), inline=True)
                                
                                if feedback_bonus_points > 0:
                                    embed.add_field(name="Bonus Points", value=f"+{feedback_bonus_points}", inline=True)
                                
                                if role_config and trust_multiplier > 1.0:
                                    embed.add_field(
                                        name="🎭 Role Bonus",
                                        value=f"×{trust_multiplier} trust from {role_config.get('name', 'your role')}!",
                                        inline=False
                                    )
                                
                                if not is_complete:
                                    embed.add_field(
                                        name="💡 Tip",
                                        value="Use `/feedback` to add a text review for bonus points!",
                                        inline=False
                                    )
                                
                                await message.author.send(embed=embed)
                            except discord.Forbidden:
                                pass
                                
            except discord.HTTPException:
                pass
            except Exception as e:
                print(f"Error processing feedback attachment: {e}")

async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))