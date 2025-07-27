# cogs/moderation.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio
from typing import Optional, Union

class ModerationView(discord.ui.View):
    def __init__(self, action_type: str):
        super().__init__(timeout=60)
        self.action_type = action_type
        self.confirmed = False
        
    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()

class AppealModal(discord.ui.Modal, title="📝 Blacklist Appeal"):
    def __init__(self):
        super().__init__()
        
        self.reason = discord.ui.TextInput(
            label="Why should we unblacklist you?",
            style=discord.TextStyle.paragraph,
            placeholder="Explain your situation...",
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)
        
        self.promise = discord.ui.TextInput(
            label="What will you do differently?",
            style=discord.TextStyle.paragraph,
            placeholder="How will you follow the rules...",
            required=True,
            max_length=500
        )
        self.add_item(self.promise)

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_punishments.start()
        self.auto_moderate.start()
        
    def cog_unload(self):
        self.check_punishments.cancel()
        self.auto_moderate.cancel()
        
    async def is_moderator(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
            
        server = await self.db.servers.find_one({"server_id": member.guild.id})
        if server:
            mod_roles = server.get("mod_roles", [])
            for role in member.roles:
                if role.id in mod_roles:
                    return True
                    
        return False
    
    async def log_moderation(self, guild_id: int, action: str, moderator: discord.Member, target: discord.Member, reason: str):
        embed = discord.Embed(
            title=f"🔨 Moderation Action: {action}",
            color=0xff0000,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👮 Moderator", value=f"{moderator.mention}\n`{moderator.id}`", inline=True)
        embed.add_field(name="🎯 Target", value=f"{target.mention}\n`{target.id}`", inline=True)
        embed.add_field(name="📝 Reason", value=reason or "No reason provided", inline=False)
        
        await self.db.moderation.insert_one({
            "guild_id": guild_id,
            "action": action,
            "moderator_id": moderator.id,
            "target_id": target.id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc)
        })
        
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, embed=embed)
    
    @tasks.loop(minutes=5)
    async def check_punishments(self):
        try:
            now = datetime.now(timezone.utc)
            
            expired_blacklists = await self.db.users.find({
                "blacklisted": True,
                "blacklist_expires": {"$lte": now}
            }).to_list(None)
            
            for user in expired_blacklists:
                await self.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {
                        "$set": {"blacklisted": False},
                        "$unset": {"blacklist_expires": ""}
                    }
                )
                
            expired_mutes = await self.db.punishments.find({
                "type": "mute",
                "active": True,
                "expires": {"$lte": now}
            }).to_list(None)
            
            for mute in expired_mutes:
                guild = self.bot.get_guild(mute["guild_id"])
                if guild:
                    member = guild.get_member(mute["user_id"])
                    mute_role = discord.utils.get(guild.roles, name="Cookie Muted")
                    if member and mute_role and mute_role in member.roles:
                        await member.remove_roles(mute_role, reason="Mute expired")
                        
                await self.db.punishments.update_one(
                    {"_id": mute["_id"]},
                    {"$set": {"active": False}}
                )
                
        except Exception as e:
            self.bot.logger.error(f"Error checking punishments: {e}")
    
    @tasks.loop(minutes=1)
    async def auto_moderate(self):
        try:
            suspicious_users = await self.db.users.find({
                "$or": [
                    {"total_claims": {"$gt": 50}, "trust_score": {"$lt": 30}},
                    {"weekly_claims": {"$gt": 20}}
                ]
            }).to_list(None)
            
            for user in suspicious_users:
                if not user.get("auto_flagged"):
                    await self.db.users.update_one(
                        {"user_id": user["user_id"]},
                        {"$set": {"auto_flagged": True, "flag_reason": "Suspicious activity detected"}}
                    )
                    
                    config = await self.db.config.find_one({"_id": "bot_config"})
                    if config and config.get("main_log_channel"):
                        channel = self.bot.get_channel(config["main_log_channel"])
                        if channel:
                            embed = discord.Embed(
                                title="🚨 Suspicious Activity",
                                description=f"User <@{user['user_id']}> flagged for review",
                                color=0xffa500,
                                timestamp=datetime.now(timezone.utc)
                            )
                            embed.add_field(name="Claims", value=f"Total: {user['total_claims']}\nWeekly: {user['weekly_claims']}", inline=True)
                            embed.add_field(name="Trust Score", value=user['trust_score'], inline=True)
                            await channel.send(embed=embed)
                            
        except Exception as e:
            self.bot.logger.error(f"Error in auto moderation: {e}")

    @commands.hybrid_command(name="warn", description="Warn a user")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, user: discord.Member, *, reason: str = None):
        if user.bot:
            await ctx.send("❌ Cannot warn bots!", ephemeral=True)
            return
            
        if user.id == ctx.author.id:
            await ctx.send("❌ Cannot warn yourself!", ephemeral=True)
            return
            
        if user.top_role >= ctx.author.top_role:
            await ctx.send("❌ Cannot warn users with equal or higher roles!", ephemeral=True)
            return
        
        warnings = await self.db.warnings.count_documents({
            "guild_id": ctx.guild.id,
            "user_id": user.id
        })
        
        await self.db.warnings.insert_one({
            "guild_id": ctx.guild.id,
            "user_id": user.id,
            "moderator_id": ctx.author.id,
            "reason": reason or "No reason provided",
            "timestamp": datetime.now(timezone.utc),
            "warning_number": warnings + 1
        })
        
        embed = discord.Embed(
            title="⚠️ User Warned",
            description=f"{user.mention} has been warned",
            color=0xffa500,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Warning #", value=warnings + 1, inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
        embed.set_footer(text=f"Warned by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="⚠️ You've Been Warned",
                description=f"You were warned in **{ctx.guild.name}**",
                color=0xffa500,
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            dm_embed.add_field(name="Warning Count", value=f"This is warning #{warnings + 1}", inline=False)
            dm_embed.set_footer(text="Multiple warnings may result in blacklist")
            
            await user.send(embed=dm_embed)
        except:
            pass
        
        await self.log_moderation(ctx.guild.id, "WARN", ctx.author, user, reason)
        
        if warnings + 1 >= 3:
            embed = discord.Embed(
                title="🚨 Auto-Action Triggered",
                description=f"{user.mention} has **{warnings + 1}** warnings!",
                color=0xff0000
            )
            embed.add_field(name="Recommended Action", value="Consider blacklisting this user", inline=False)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="mute", description="Mute a user from using the bot")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, user: discord.Member, duration: str = "1h", *, reason: str = None):
        if user.bot:
            await ctx.send("❌ Cannot mute bots!", ephemeral=True)
            return
            
        if user.id == ctx.author.id:
            await ctx.send("❌ Cannot mute yourself!", ephemeral=True)
            return
            
        if user.top_role >= ctx.author.top_role:
            await ctx.send("❌ Cannot mute users with equal or higher roles!", ephemeral=True)
            return
        
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = duration[-1].lower()
        if unit not in time_units:
            await ctx.send("❌ Invalid duration! Use: 1s, 1m, 1h, 1d", ephemeral=True)
            return
            
        try:
            amount = int(duration[:-1])
            seconds = amount * time_units[unit]
            if seconds > 2592000:  # 30 days
                await ctx.send("❌ Maximum mute duration is 30 days!", ephemeral=True)
                return
        except:
            await ctx.send("❌ Invalid duration format!", ephemeral=True)
            return
        
        mute_role = discord.utils.get(ctx.guild.roles, name="Cookie Muted")
        if not mute_role:
            mute_role = await ctx.guild.create_role(
                name="Cookie Muted",
                color=discord.Color.dark_gray(),
                reason="Cookie Bot mute role"
            )
        
        await user.add_roles(mute_role, reason=f"Muted by {ctx.author}: {reason}")
        
        expires = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        
        await self.db.punishments.insert_one({
            "guild_id": ctx.guild.id,
            "user_id": user.id,
            "type": "mute",
            "moderator_id": ctx.author.id,
            "reason": reason,
            "duration": duration,
            "expires": expires,
            "active": True,
            "timestamp": datetime.now(timezone.utc)
        })
        
        embed = discord.Embed(
            title="🔇 User Muted",
            description=f"{user.mention} has been muted from using the bot",
            color=0xff6600,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Expires", value=f"<t:{int(expires.timestamp())}:R>", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.set_footer(text=f"Muted by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="🔇 You've Been Muted",
                description=f"You were muted in **{ctx.guild.name}**",
                color=0xff6600,
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.add_field(name="Duration", value=duration, inline=True)
            dm_embed.add_field(name="Expires", value=f"<t:{int(expires.timestamp())}:R>", inline=True)
            dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            
            await user.send(embed=dm_embed)
        except:
            pass
        
        await self.log_moderation(ctx.guild.id, "MUTE", ctx.author, user, f"{reason} (Duration: {duration})")

    @commands.hybrid_command(name="unmute", description="Unmute a user")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, user: discord.Member):
        mute_role = discord.utils.get(ctx.guild.roles, name="Cookie Muted")
        if not mute_role or mute_role not in user.roles:
            await ctx.send("❌ User is not muted!", ephemeral=True)
            return
        
        await user.remove_roles(mute_role, reason=f"Unmuted by {ctx.author}")
        
        await self.db.punishments.update_many(
            {
                "guild_id": ctx.guild.id,
                "user_id": user.id,
                "type": "mute",
                "active": True
            },
            {"$set": {"active": False}}
        )
        
        embed = discord.Embed(
            title="🔊 User Unmuted",
            description=f"{user.mention} has been unmuted",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Unmuted by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)
        await self.log_moderation(ctx.guild.id, "UNMUTE", ctx.author, user, "Manual unmute")

    @commands.hybrid_command(name="blacklist", description="Blacklist a user from the bot")
    @commands.has_permissions(administrator=True)
    async def blacklist_user(self, ctx, user: Union[discord.Member, discord.User], days: int = 30, *, reason: str = None):
        if isinstance(user, discord.Member) and user.bot:
            await ctx.send("❌ Cannot blacklist bots!", ephemeral=True)
            return
            
        if user.id == ctx.author.id:
            await ctx.send("❌ Cannot blacklist yourself!", ephemeral=True)
            return
        
        view = ModerationView("blacklist")
        embed = discord.Embed(
            title="⚠️ Confirm Blacklist",
            description=f"Are you sure you want to blacklist {user.mention} for **{days}** days?",
            color=0xff0000
        )
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.add_field(name="Effects", value="• Cannot use any bot commands\n• Cannot claim cookies\n• Loses access to all features", inline=False)
        
        message = await ctx.send(embed=embed, view=view)
        await view.wait()
        
        if not view.confirmed:
            await message.edit(content="❌ Blacklist cancelled", embed=None, view=None)
            return
        
        expire_date = datetime.now(timezone.utc) + timedelta(days=days)
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "blacklisted": True,
                    "blacklist_expires": expire_date,
                    "blacklist_reason": reason,
                    "blacklisted_by": ctx.author.id
                }
            },
            upsert=True
        )
        
        success_embed = discord.Embed(
            title="🚫 User Blacklisted",
            description=f"{user.mention} has been blacklisted",
            color=0xff0000,
            timestamp=datetime.now(timezone.utc)
        )
        success_embed.add_field(name="Duration", value=f"{days} days", inline=True)
        success_embed.add_field(name="Expires", value=f"<t:{int(expire_date.timestamp())}:R>", inline=True)
        success_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        success_embed.set_footer(text=f"Blacklisted by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await message.edit(embed=success_embed, view=None)
        
        try:
            dm_embed = discord.Embed(
                title="🚫 You've Been Blacklisted",
                description=f"You were blacklisted from using Cookie Bot",
                color=0xff0000,
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.add_field(name="Duration", value=f"{days} days", inline=True)
            dm_embed.add_field(name="Expires", value=f"<t:{int(expire_date.timestamp())}:F>", inline=True)
            dm_embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            dm_embed.add_field(
                name="Appeal",
                value=f"You can appeal this decision by joining our [support server]({os.getenv('MAIN_SERVER_INVITE')})",
                inline=False
            )
            
            await user.send(embed=dm_embed)
        except:
            pass
        
        await self.log_moderation(ctx.guild.id, "BLACKLIST", ctx.author, user, f"{reason} (Duration: {days} days)")

    @commands.hybrid_command(name="unblacklist", description="Remove a user from blacklist")
    @commands.has_permissions(administrator=True)
    async def unblacklist(self, ctx, user: Union[discord.Member, discord.User]):
        user_data = await self.db.users.find_one({"user_id": user.id})
        
        if not user_data or not user_data.get("blacklisted"):
            await ctx.send("❌ User is not blacklisted!", ephemeral=True)
            return
        
        await self.db.users.update_one(
            {"user_id": user.id},
            {
                "$set": {"blacklisted": False},
                "$unset": {"blacklist_expires": "", "blacklist_reason": "", "blacklisted_by": ""}
            }
        )
        
        embed = discord.Embed(
            title="✅ User Unblacklisted",
            description=f"{user.mention} has been removed from blacklist",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Unblacklisted by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title="✅ Blacklist Removed",
                description="Your blacklist has been removed! You can now use Cookie Bot again.",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            await user.send(embed=dm_embed)
        except:
            pass
        
        await self.log_moderation(ctx.guild.id, "UNBLACKLIST", ctx.author, user, "Manual removal")

    @commands.hybrid_command(name="warnings", description="View warnings for a user")
    async def warnings(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.author
            
        warnings = await self.db.warnings.find({
            "guild_id": ctx.guild.id,
            "user_id": user.id
        }).sort("timestamp", -1).to_list(10)
        
        if not warnings:
            embed = discord.Embed(
                title="✅ No Warnings",
                description=f"{user.mention} has no warnings!",
                color=0x00ff00
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"⚠️ Warnings for {user.display_name}",
            description=f"Total warnings: **{len(warnings)}**",
            color=0xffa500,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        for i, warning in enumerate(warnings[:5]):
            moderator = self.bot.get_user(warning["moderator_id"])
            mod_name = moderator.name if moderator else "Unknown"
            
            embed.add_field(
                name=f"Warning #{warning['warning_number']}",
                value=f"**Reason:** {warning['reason']}\n**By:** {mod_name}\n**Date:** <t:{int(warning['timestamp'].timestamp())}:R>",
                inline=False
            )
        
        if len(warnings) > 5:
            embed.set_footer(text=f"Showing 5 of {len(warnings)} warnings")
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarnings", description="Clear warnings for a user")
    @commands.has_permissions(administrator=True)
    async def clearwarnings(self, ctx, user: discord.Member):
        count = await self.db.warnings.count_documents({
            "guild_id": ctx.guild.id,
            "user_id": user.id
        })
        
        if count == 0:
            await ctx.send("❌ User has no warnings!", ephemeral=True)
            return
        
        await self.db.warnings.delete_many({
            "guild_id": ctx.guild.id,
            "user_id": user.id
        })
        
        embed = discord.Embed(
            title="✅ Warnings Cleared",
            description=f"Cleared **{count}** warnings for {user.mention}",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Cleared by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)
        await self.log_moderation(ctx.guild.id, "CLEAR_WARNINGS", ctx.author, user, f"Cleared {count} warnings")

    @commands.hybrid_command(name="modlogs", description="View moderation logs")
    @commands.has_permissions(moderate_members=True)
    async def modlogs(self, ctx, user: Optional[discord.Member] = None):
        query = {"guild_id": ctx.guild.id}
        if user:
            query["target_id"] = user.id
            
        logs = await self.db.moderation.find(query).sort("timestamp", -1).limit(10).to_list(10)
        
        if not logs:
            embed = discord.Embed(
                title="📋 No Logs Found",
                description="No moderation logs found for the specified criteria",
                color=0x5865f2
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Moderation Logs",
            description=f"Showing recent moderation actions{f' for {user.mention}' if user else ''}",
            color=0x5865f2,
            timestamp=datetime.now(timezone.utc)
        )
        
        for log in logs[:5]:
            moderator = self.bot.get_user(log["moderator_id"])
            target = self.bot.get_user(log["target_id"])
            
            embed.add_field(
                name=f"{log['action']} - <t:{int(log['timestamp'].timestamp())}:R>",
                value=f"**Mod:** {moderator.mention if moderator else 'Unknown'}\n**Target:** {target.mention if target else 'Unknown'}\n**Reason:** {log.get('reason', 'No reason')}",
                inline=False
            )
        
        if len(logs) > 5:
            embed.set_footer(text=f"Showing 5 of {len(logs)} logs")
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="appeal", description="Appeal your blacklist")
    async def appeal(self, ctx):
        user_data = await self.db.users.find_one({"user_id": ctx.author.id})
        
        if not user_data or not user_data.get("blacklisted"):
            await ctx.send("❌ You are not blacklisted!", ephemeral=True)
            return
        
        last_appeal = user_data.get("last_appeal")
        if last_appeal and datetime.now(timezone.utc) - last_appeal < timedelta(days=3):
            next_appeal = last_appeal + timedelta(days=3)
            await ctx.send(
                f"❌ You can appeal again <t:{int(next_appeal.timestamp())}:R>",
                ephemeral=True
            )
            return
        
        modal = AppealModal()
        await ctx.interaction.response.send_modal(modal)
        
        await modal.wait()
        
        await self.db.users.update_one(
            {"user_id": ctx.author.id},
            {"$set": {"last_appeal": datetime.now(timezone.utc)}}
        )
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("appeals_channel"):
            channel = self.bot.get_channel(config["appeals_channel"])
            if channel:
                embed = discord.Embed(
                    title="📝 New Blacklist Appeal",
                    color=0x5865f2,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
                embed.add_field(name="User ID", value=f"`{ctx.author.id}`", inline=True)
                embed.add_field(
                    name="Blacklist Expires",
                    value=f"<t:{int(user_data['blacklist_expires'].timestamp())}:R>",
                    inline=True
                )
                embed.add_field(
                    name="Original Reason",
                    value=user_data.get("blacklist_reason", "No reason recorded"),
                    inline=False
                )
                embed.add_field(name="Appeal Reason", value=modal.reason.value, inline=False)
                embed.add_field(name="Promise", value=modal.promise.value, inline=False)
                
                appeal_view = discord.ui.View()
                approve = discord.ui.Button(label="✅ Approve", style=discord.ButtonStyle.success)
                deny = discord.ui.Button(label="❌ Deny", style=discord.ButtonStyle.danger)
                
                async def approve_callback(interaction: discord.Interaction):
                    if not interaction.user.guild_permissions.administrator:
                        await interaction.response.send_message("❌ Only admins can approve appeals!", ephemeral=True)
                        return
                    
                    await self.db.users.update_one(
                        {"user_id": ctx.author.id},
                        {
                            "$set": {"blacklisted": False},
                            "$unset": {"blacklist_expires": "", "blacklist_reason": ""}
                        }
                    )
                    
                    await interaction.response.edit_message(
                        content=f"✅ Appeal approved by {interaction.user.mention}",
                        embed=embed,
                        view=None
                    )
                    
                    try:
                        await ctx.author.send("✅ Your blacklist appeal has been **approved**! You can now use Cookie Bot again.")
                    except:
                        pass
                
                async def deny_callback(interaction: discord.Interaction):
                    if not interaction.user.guild_permissions.administrator:
                        await interaction.response.send_message("❌ Only admins can deny appeals!", ephemeral=True)
                        return
                    
                    await interaction.response.edit_message(
                        content=f"❌ Appeal denied by {interaction.user.mention}",
                        embed=embed,
                        view=None
                    )
                    
                    try:
                        await ctx.author.send("❌ Your blacklist appeal has been **denied**. You can appeal again in 3 days.")
                    except:
                        pass
                
                approve.callback = approve_callback
                deny.callback = deny_callback
                
                appeal_view.add_item(approve)
                appeal_view.add_item(deny)
                
                await channel.send(embed=embed, view=appeal_view)
        
        success_embed = discord.Embed(
            title="✅ Appeal Submitted",
            description="Your appeal has been submitted for review!",
            color=0x00ff00
        )
        success_embed.add_field(
            name="⏰ Next Appeal",
            value="You can appeal again in 3 days if this is denied",
            inline=False
        )
        
        await ctx.followup.send(embed=success_embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))