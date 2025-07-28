import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import traceback
from typing import Optional, Dict, List

class InviteLeaderboardView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.current_page = 0
        self.items_per_page = 10
        
    async def get_leaderboard_data(self):
        users = await self.cog.db.users.find(
            {"invite_count": {"$gt": 0}}
        ).sort("invite_count", -1).limit(50).to_list(None)
        return users
    
    async def create_embed(self):
        users = await self.get_leaderboard_data()
        
        total_pages = (len(users) - 1) // self.items_per_page + 1
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        
        embed = discord.Embed(
            title="👥 Invite Leaderboard",
            description="Top inviters in the server",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        leaderboard_text = ""
        for idx, user_data in enumerate(users[start:end], start=start+1):
            user = self.cog.bot.get_user(user_data["user_id"])
            username = user.name if user else user_data.get("username", "Unknown")
            invites = user_data.get("invite_count", 0)
            
            medal = ""
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            
            leaderboard_text += f"{medal} **{idx}.** {username} - **{invites}** invites\n"
        
        embed.description = leaderboard_text or "No invites recorded yet!"
        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        
        return embed
    
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.gray)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        await interaction.response.edit_message(embed=await self.create_embed(), view=self)
    
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = await self.get_leaderboard_data()
        max_pages = (len(users) - 1) // self.items_per_page
        self.current_page = min(max_pages, self.current_page + 1)
        await interaction.response.edit_message(embed=await self.create_embed(), view=self)

class InviteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.invites = {}
        self.verified_role_id = 1349289354329198623
        self.invite_cache_update.start()
        self.pending_rewards = {}
        self.tracked_members = {}
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def get_or_create_user(self, user_id: int, username: str):
        user = await self.db.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "username": username,
                "points": 0,
                "total_earned": 0,
                "total_spent": 0,
                "trust_score": 50,
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "daily_claimed": None,
                "invite_count": 0,
                "pending_invites": 0,
                "verified_invites": 0,
                "fake_invites": 0,
                "last_claim": None,
                "cookie_claims": {},
                "weekly_claims": 0,
                "total_claims": 0,
                "blacklisted": False,
                "blacklist_expires": None,
                "invited_users": []
            }
            await self.db.users.insert_one(user)
        return user
    
    @tasks.loop(minutes=30)
    async def invite_cache_update(self):
        for guild in self.bot.guilds:
            try:
                self.invites[guild.id] = await guild.invites()
            except:
                pass
    
    @invite_cache_update.before_loop
    async def before_invite_cache_update(self):
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(2)
        for guild in self.bot.guilds:
            try:
                self.invites[guild.id] = await guild.invites()
            except Exception as e:
                print(f"Failed to cache invites for {guild.name}: {e}")
    
    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        try:
            self.invites[invite.guild.id] = await invite.guild.invites()
        except:
            pass
    
    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        try:
            self.invites[invite.guild.id] = await invite.guild.invites()
        except:
            pass
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            if member.bot:
                return
                
            guild = member.guild
            
            if guild.id not in self.invites:
                self.invites[guild.id] = await guild.invites()
                return
            
            old_invites = self.invites[guild.id]
            new_invites = await guild.invites()
            self.invites[guild.id] = new_invites
            
            used_invite = None
            for invite in old_invites:
                matching = next((i for i in new_invites if i.code == invite.code), None)
                if matching and matching.uses > invite.uses:
                    used_invite = matching
                    break
            
            if used_invite and used_invite.inviter:
                inviter_data = await self.get_or_create_user(used_invite.inviter.id, str(used_invite.inviter))
                
                await self.db.users.update_one(
                    {"user_id": used_invite.inviter.id},
                    {
                        "$inc": {"invite_count": 1, "pending_invites": 1},
                        "$push": {"invited_users": {
                            "user_id": member.id,
                            "username": str(member),
                            "joined_at": datetime.now(timezone.utc),
                            "verified": False,
                            "invite_code": used_invite.code
                        }}
                    }
                )
                
                self.tracked_members[member.id] = {
                    "inviter_id": used_invite.inviter.id,
                    "joined_at": datetime.now(timezone.utc),
                    "guild_id": guild.id
                }
                
                embed = discord.Embed(
                    title="👋 New Member Joined!",
                    description=f"{member.mention} joined using an invite",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Invited By", value=used_invite.inviter.mention, inline=True)
                embed.add_field(name="Invite Code", value=f"`{used_invite.code}`", inline=True)
                embed.add_field(name="Total Uses", value=f"**{matching.uses}**", inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Member #{guild.member_count}")
                
                await self.log_action(
                    guild.id,
                    f"👋 {member.mention} joined using invite from {used_invite.inviter.mention} (Code: `{used_invite.code}`)",
                    discord.Color.blue()
                )
                
                if used_invite.inviter.id not in self.pending_rewards:
                    self.pending_rewards[used_invite.inviter.id] = []
                self.pending_rewards[used_invite.inviter.id].append(member.id)
                
                try:
                    dm_embed = discord.Embed(
                        title="🎉 Someone joined using your invite!",
                        description=f"{member.name} joined **{guild.name}** using your invite link!",
                        color=discord.Color.green()
                    )
                    dm_embed.add_field(name="Invite Code", value=f"`{used_invite.code}`", inline=True)
                    dm_embed.add_field(name="Total Invites", value=f"**{inviter_data.get('invite_count', 0) + 1}**", inline=True)
                    dm_embed.set_footer(text="You'll receive points when they get verified!")
                    
                    await used_invite.inviter.send(embed=dm_embed)
                except:
                    pass
                    
        except Exception as e:
            print(f"Error tracking invite: {traceback.format_exc()}")
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        try:
            if before.bot:
                return
            
            verified_role = after.guild.get_role(self.verified_role_id)
            if not verified_role:
                return
            
            had_role = verified_role in before.roles
            has_role = verified_role in after.roles
            
            if not had_role and has_role:
                config = await self.db.config.find_one({"_id": "bot_config"})
                invite_points = config.get("point_rates", {}).get("invite", 2)
                
                member_data = self.tracked_members.get(after.id)
                if member_data:
                    inviter_id = member_data["inviter_id"]
                    
                    await self.db.users.update_one(
                        {
                            "user_id": inviter_id,
                            "invited_users.user_id": after.id
                        },
                        {
                            "$set": {"invited_users.$.verified": True},
                            "$inc": {
                                "pending_invites": -1,
                                "verified_invites": 1,
                                "points": invite_points,
                                "total_earned": invite_points
                            }
                        }
                    )
                    
                    inviter = self.bot.get_user(inviter_id)
                    if inviter:
                        embed = discord.Embed(
                            title="💰 Invite Reward Earned!",
                            description=f"{after.mention} has been verified!",
                            color=discord.Color.green(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        embed.add_field(name="Points Earned", value=f"**+{invite_points}** points", inline=True)
                        embed.add_field(name="Member", value=after.name, inline=True)
                        embed.set_thumbnail(url=after.display_avatar.url)
                        
                        await self.log_action(
                            after.guild.id,
                            f"✅ {inviter.mention} received **{invite_points}** points for inviting {after.mention} (Verified)",
                            discord.Color.green()
                        )
                        
                        try:
                            await inviter.send(embed=embed)
                        except:
                            pass
                    
                    del self.tracked_members[after.id]
                else:
                    user_data = await self.db.users.find_one({"invited_users.user_id": after.id})
                    if user_data:
                        for invited in user_data.get("invited_users", []):
                            if invited["user_id"] == after.id and not invited.get("verified"):
                                await self.db.users.update_one(
                                    {
                                        "user_id": user_data["user_id"],
                                        "invited_users.user_id": after.id
                                    },
                                    {
                                        "$set": {"invited_users.$.verified": True},
                                        "$inc": {
                                            "pending_invites": -1,
                                            "verified_invites": 1,
                                            "points": invite_points,
                                            "total_earned": invite_points
                                        }
                                    }
                                )
                                
                                inviter = self.bot.get_user(user_data["user_id"])
                                if inviter:
                                    await self.log_action(
                                        after.guild.id,
                                        f"✅ {inviter.mention} received **{invite_points}** points for inviting {after.mention} (Verified - Database Recovery)",
                                        discord.Color.green()
                                    )
                                break
                
                if after.id in self.pending_rewards:
                    for inviter_id in list(self.pending_rewards.keys()):
                        if after.id in self.pending_rewards[inviter_id]:
                            self.pending_rewards[inviter_id].remove(after.id)
                            if not self.pending_rewards[inviter_id]:
                                del self.pending_rewards[inviter_id]
                                
        except Exception as e:
            print(f"Error in member update: {traceback.format_exc()}")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            if member.bot:
                return
            
            if member.id in self.tracked_members:
                del self.tracked_members[member.id]
            
            user_data = await self.db.users.find_one({"invited_users.user_id": member.id})
            if user_data:
                for invited in user_data.get("invited_users", []):
                    if invited["user_id"] == member.id:
                        if invited.get("verified"):
                            await self.db.users.update_one(
                                {"user_id": user_data["user_id"]},
                                {
                                    "$inc": {"verified_invites": -1},
                                    "$pull": {"invited_users": {"user_id": member.id}}
                                }
                            )
                        else:
                            await self.db.users.update_one(
                                {"user_id": user_data["user_id"]},
                                {
                                    "$inc": {"pending_invites": -1, "fake_invites": 1},
                                    "$pull": {"invited_users": {"user_id": member.id}}
                                }
                            )
                        
                        inviter = self.bot.get_user(user_data["user_id"])
                        if inviter:
                            embed = discord.Embed(
                                title="👋 Invited Member Left",
                                description=f"{member.name} left the server",
                                color=discord.Color.orange(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            embed.add_field(name="Status", value="Not Verified" if not invited.get("verified") else "Was Verified", inline=True)
                            embed.add_field(name="Stayed For", value=f"{(datetime.now(timezone.utc) - invited['joined_at']).days} days", inline=True)
                            
                            await self.log_action(
                                member.guild.id,
                                f"👋 {member.mention} left (Invited by {inviter.mention})",
                                discord.Color.orange()
                            )
                        break
                        
        except Exception as e:
            print(f"Error in member remove: {e}")
    
    @commands.hybrid_command(name="invites", description="Check invite statistics")
    @app_commands.describe(user="The user to check invites for (leave empty for yourself)")
    async def invites(self, ctx, user: Optional[discord.Member] = None):
        try:
            if user is None:
                user = ctx.author
            
            user_data = await self.db.users.find_one({"user_id": user.id})
            
            config = await self.db.config.find_one({"_id": "bot_config"})
            invite_points = config.get("point_rates", {}).get("invite", 2)
            
            embed = discord.Embed(
                title=f"📨 Invite Statistics: {user.display_name}",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            if not user_data:
                embed.description = "No invite data found for this user!"
                embed.add_field(name="Total Invites", value="**0**", inline=True)
                embed.add_field(name="Points per Invite", value=f"**{invite_points}**", inline=True)
            else:
                total_invites = user_data.get("invite_count", 0)
                pending = user_data.get("pending_invites", 0)
                verified = user_data.get("verified_invites", 0)
                fake = user_data.get("fake_invites", 0)
                
                embed.add_field(name="📊 Total Invites", value=f"**{total_invites}**", inline=True)
                embed.add_field(name="✅ Verified", value=f"**{verified}**", inline=True)
                embed.add_field(name="⏳ Pending", value=f"**{pending}**", inline=True)
                
                embed.add_field(name="💰 Points Earned", value=f"**{verified * invite_points}**", inline=True)
                embed.add_field(name="💸 Potential Points", value=f"**{pending * invite_points}**", inline=True)
                embed.add_field(name="❌ Left/Fake", value=f"**{fake}**", inline=True)
                
                verified_role = ctx.guild.get_role(self.verified_role_id)
                if verified_role:
                    if verified_role in user.roles:
                        embed.add_field(
                            name="✅ Verification Status",
                            value="You have the verified role!",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="❌ Verification Status",
                            value=f"Get <@&{self.verified_role_id}> to earn invite rewards!",
                            inline=False
                        )
                
                recent_invites = user_data.get("invited_users", [])[-5:]
                if recent_invites:
                    recent_text = []
                    for inv in reversed(recent_invites):
                        status = "✅" if inv.get("verified") else "⏳"
                        recent_text.append(f"{status} {inv['username']}")
                    
                    embed.add_field(
                        name="📋 Recent Invites",
                        value="\n".join(recent_text),
                        inline=False
                    )
            
            guild_invites = await ctx.guild.invites()
            user_invites = [inv for inv in guild_invites if inv.inviter == user]
            
            if user_invites:
                active_text = []
                for inv in user_invites[:3]:
                    active_text.append(f"`{inv.code}` - {inv.uses} uses")
                
                embed.add_field(
                    name="🔗 Active Invite Links",
                    value="\n".join(active_text),
                    inline=False
                )
            
            embed.set_footer(text=f"Points per verified invite: {invite_points}")
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in invites command: {traceback.format_exc()}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="inviteleaderboard", description="View the top inviters")
    async def inviteleaderboard(self, ctx):
        try:
            view = InviteLeaderboardView(self, ctx.guild.id)
            embed = await view.create_embed()
            
            await ctx.send(embed=embed, view=view, ephemeral=False)
            
        except Exception as e:
            print(f"Error in inviteleaderboard: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="createinvite", description="Create a tracked invite link")
    @app_commands.describe(
        uses="Maximum uses (0 for unlimited)",
        expires="Expiration time in hours (0 for never)"
    )
    async def createinvite(self, ctx, uses: int = 0, expires: int = 0):
        try:
            max_age = expires * 3600 if expires > 0 else 0
            
            invite = await ctx.channel.create_invite(
                max_uses=uses,
                max_age=max_age,
                reason=f"Created by {ctx.author} via bot command"
            )
            
            embed = discord.Embed(
                title="🔗 Invite Link Created!",
                description=f"Your personalized invite link is ready",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Link", value=f"`{invite.url}`", inline=False)
            embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
            embed.add_field(name="Max Uses", value=f"**{uses if uses > 0 else 'Unlimited'}**", inline=True)
            embed.add_field(name="Expires", value=f"**{f'{expires} hours' if expires > 0 else 'Never'}**", inline=True)
            
            embed.add_field(
                name="💡 Tip",
                value="Share this link to earn points when people join and get verified!",
                inline=False
            )
            
            embed.set_footer(text=f"Created by {ctx.author}")
            
            await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error creating invite: {e}")
            await ctx.send("❌ Failed to create invite! Check my permissions.", ephemeral=True)
    
    @commands.hybrid_command(name="resetinvites", description="Reset invite count for a user (Admin only)")
    @app_commands.describe(user="The user to reset invites for")
    @commands.has_permissions(administrator=True)
    async def resetinvites(self, ctx, user: discord.Member):
        try:
            await self.db.users.update_one(
                {"user_id": user.id},
                {
                    "$set": {
                        "invite_count": 0,
                        "pending_invites": 0,
                        "verified_invites": 0,
                        "fake_invites": 0,
                        "invited_users": []
                    }
                }
            )
            
            embed = discord.Embed(
                title="🔄 Invites Reset",
                description=f"Invite statistics have been reset for {user.mention}",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Reset by {ctx.author}")
            
            await ctx.send(embed=embed)
            
            await self.log_action(
                ctx.guild.id,
                f"🔄 {ctx.author.mention} reset invites for {user.mention}",
                discord.Color.orange()
            )
            
        except Exception as e:
            print(f"Error resetting invites: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)
    
    @commands.hybrid_command(name="syncvites", description="Sync invite data from database (Owner only)")
    @commands.is_owner()
    async def syncvites(self, ctx):
        try:
            await ctx.defer()
            
            synced = 0
            async for user_data in self.db.users.find({"invited_users": {"$exists": True, "$ne": []}}):
                for invited in user_data.get("invited_users", []):
                    if not invited.get("verified"):
                        member_id = invited["user_id"]
                        member = ctx.guild.get_member(member_id)
                        
                        if member:
                            verified_role = ctx.guild.get_role(self.verified_role_id)
                            if verified_role and verified_role in member.roles:
                                config = await self.db.config.find_one({"_id": "bot_config"})
                                invite_points = config.get("point_rates", {}).get("invite", 2)
                                
                                await self.db.users.update_one(
                                    {
                                        "user_id": user_data["user_id"],
                                        "invited_users.user_id": member_id
                                    },
                                    {
                                        "$set": {"invited_users.$.verified": True},
                                        "$inc": {
                                            "pending_invites": -1,
                                            "verified_invites": 1,
                                            "points": invite_points,
                                            "total_earned": invite_points
                                        }
                                    }
                                )
                                synced += 1
            
            embed = discord.Embed(
                title="✅ Invite Sync Complete",
                description=f"Synced **{synced}** pending invites that were already verified",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error syncing invites: {e}")
            await ctx.send("❌ An error occurred!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(InviteCog(bot))