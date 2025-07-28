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
            if last_claim.get("feedback_given"):
                await interaction.response.send_message("✅ You already submitted feedback!", ephemeral=True)
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
                        "trust_score": 0.25,  # 0.25 for optional text feedback
                        "statistics.feedback_streak": 1
                    }
                }
            )
            
            await self.db.feedback.insert_one({
                "user_id": interaction.user.id,
                "cookie_type": last_claim["type"],
                "file": last_claim["file"],
                "rating": rating,
                "feedback": feedback,
                "timestamp": datetime.now(timezone.utc),
                "server_id": interaction.guild_id,
                "has_screenshot": False
            })
            
            stars = "⭐" * rating
            embed = discord.Embed(
                title="✅ Text Feedback Submitted!",
                description=f"Thank you for rating the **{last_claim['type']}** cookie!",
                color=discord.Color.green()
            )
            embed.add_field(name="Rating", value=stars, inline=True)
            embed.add_field(name="Trust Score", value="+0.25 points", inline=True)
            embed.add_field(name="Streak", value=f"{current_streak + 1} feedback(s)", inline=True)
            
            server = await self.db.servers.find_one({"server_id": interaction.guild_id})
            if server and server.get("channels", {}).get("feedback"):
                embed.add_field(
                    name="📸 Don't Forget!",
                    value=f"Post your screenshot in <#{server['channels']['feedback']}> for bonus points!",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Don't log here - wait for screenshot or log if no screenshot comes
            
        except Exception as e:
            print(f"Error in process_feedback_submission: {e}")
            await interaction.response.send_message("❌ Error submitting feedback!", ephemeral=True)
    
    @tasks.loop(minutes=5)
    async def check_feedback_deadlines(self):
        try:
            now = datetime.now(timezone.utc)
            
            async for user in self.db.users.find({
                "last_claim": {"$exists": True},
                "last_claim.feedback_given": False,
                "blacklisted": False
            }):
                last_claim = user.get("last_claim")
                if last_claim and last_claim.get("feedback_deadline"):
                    deadline = last_claim["feedback_deadline"]
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    
                    if now > deadline:
                        await self.db.users.update_one(
                            {"user_id": user["user_id"]},
                            {
                                "$set": {
                                    "blacklisted": True,
                                    "blacklist_expires": now + timedelta(days=30),
                                    "statistics.feedback_streak": 0
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
            print(f"Error in feedback check: {e}")
    
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
            if last_claim.get("feedback_given"):
                embed = discord.Embed(
                    title="✅ Already Submitted",
                    description="You've already submitted feedback for your last cookie!",
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
            server = await self.db.servers.find_one({"server_id": message.guild.id})
            if server and message.channel.id == server["channels"].get("feedback"):
                user_data = await self.db.users.find_one({"user_id": message.author.id})
                if user_data and user_data.get("last_claim"):
                    last_claim = user_data["last_claim"]
                    
                    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
                    has_image = any(att.filename.lower().endswith(ext) for att in message.attachments for ext in image_extensions)
                    
                    if has_image:
                        cookie_type = last_claim.get("type", "unknown")
                        
                        if last_claim.get("text_feedback_only"):
                            # User already submitted text feedback (0.25), this is just the screenshot (0.5)
                            bonus = 0.5
                            embed_title = "📸 Screenshot Added to Feedback!"
                            trust_text = f"+{bonus} points (Total: 0.75)"
                        else:
                            # User is submitting screenshot without text feedback (only 0.5)
                            bonus = 0.5
                            embed_title = "✅ Screenshot Feedback Received!"
                            trust_text = f"+{bonus} points"
                            
                            await self.db.users.update_one(
                                {"user_id": message.author.id},
                                {
                                    "$set": {
                                        "last_claim.feedback_given": True,
                                        "last_claim.screenshot": True
                                    }
                                }
                            )
                        
                        await self.db.users.update_one(
                            {"user_id": message.author.id},
                            {
                                "$inc": {
                                    "trust_score": bonus,
                                    "statistics.feedback_streak": 0 if not last_claim.get("text_feedback_only") else 0
                                }
                            }
                        )
                        
                        embed = discord.Embed(
                            title=embed_title,
                            description=f"{message.author.mention} thank you for the screenshot!",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Trust Score", value=trust_text, inline=True)
                        embed.add_field(name="Cookie Type", value=cookie_type.title(), inline=True)
                        
                        await message.add_reaction("✅")
                        await message.add_reaction("📸")
                        
                        # Public feedback channel message (Style 1 with embed)
                        if last_claim.get("rating"):
                            stars = "⭐" * last_claim["rating"]
                            feedback_embed = discord.Embed(
                                description=f"{message.author.mention} rated **{cookie_type}** cookie {stars} ({last_claim['rating']}/5)",
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            if last_claim.get('feedback_text'):
                                feedback_embed.add_field(name="Feedback", value=last_claim['feedback_text'], inline=False)
                            await message.channel.send(embed=feedback_embed)
                        else:
                            feedback_embed = discord.Embed(
                                description=f"{message.author.mention} submitted feedback for **{cookie_type}** cookie",
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            await message.channel.send(embed=feedback_embed)
                        
                        # Log channel message (Style 1 text format)
                        if last_claim.get("rating"):
                            stars = "⭐" * last_claim["rating"]
                            feedback_text = f" - {last_claim.get('feedback_text', '')}" if last_claim.get('feedback_text') else ""
                            
                            await self.log_action(
                                message.guild.id,
                                f"📸 {message.author.mention} rated **{cookie_type}** cookie {stars}{feedback_text}",
                                discord.Color.green()
                            )
                        else:
                            await self.log_action(
                                message.guild.id,
                                f"📸 {message.author.mention} submitted screenshot feedback for **{cookie_type}** cookie",
                                discord.Color.green()
                            )

async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))