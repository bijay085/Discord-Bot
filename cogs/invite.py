# cogs/invite.py

import discord
from discord.ext import commands
from datetime import datetime, timezone

class InviteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.invites = {}
        self.verified_role_id = 1349289354329198623
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                self.invites[guild.id] = await guild.invites()
            except:
                pass
    
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
                inviter_data = await self.db.users.find_one({"user_id": used_invite.inviter.id})
                
                if not inviter_data:
                    inviter_data = {
                        "user_id": used_invite.inviter.id,
                        "username": str(used_invite.inviter),
                        "points": 0,
                        "total_earned": 0,
                        "total_spent": 0,
                        "trust_score": 50,
                        "account_created": datetime.now(timezone.utc),
                        "first_seen": datetime.now(timezone.utc),
                        "last_active": datetime.now(timezone.utc),
                        "daily_claimed": None,
                        "invite_count": 0,
                        "last_claim": None,
                        "cookie_claims": {},
                        "weekly_claims": 0,
                        "total_claims": 0,
                        "blacklisted": False,
                        "blacklist_expires": None
                    }
                    await self.db.users.insert_one(inviter_data)
                
                await self.db.users.update_one(
                    {"user_id": used_invite.inviter.id},
                    {"$inc": {"invite_count": 1}}
                )
                
                await self.log_action(
                    guild.id,
                    f"👋 {member.mention} joined using invite from {used_invite.inviter.mention}",
                    discord.Color.blue()
                )
                
        except Exception as e:
            print(f"Error tracking invite: {e}")
    
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
                invite_logs = []
                async for entry in after.guild.audit_logs(action=discord.AuditLogAction.invite_create, limit=50):
                    if entry.target.inviter == after:
                        invite_logs.append(entry)
                
                config = await self.db.config.find_one({"_id": "bot_config"})
                invite_points = config["point_rates"]["invite"]
                
                user_data = await self.db.users.find_one({"user_id": after.id})
                if user_data and user_data.get("invite_count", 0) > 0:
                    points_to_add = user_data["invite_count"] * invite_points
                    
                    await self.db.users.update_one(
                        {"user_id": after.id},
                        {
                            "$inc": {
                                "points": points_to_add,
                                "total_earned": points_to_add
                            }
                        }
                    )
                    
                    await self.log_action(
                        after.guild.id,
                        f"✅ {after.mention} received **{points_to_add}** points for **{user_data['invite_count']}** invites (Verified role received)",
                        discord.Color.green()
                    )
                    
                    try:
                        await after.send(
                            f"🎉 Congratulations! You received **{points_to_add}** points for inviting **{user_data['invite_count']}** members!\n"
                            f"Your invites were verified when you got the Verified role."
                        )
                    except:
                        pass
                        
        except Exception as e:
            print(f"Error in member update: {e}")
    
    @commands.hybrid_command(name="invites", description="Check your invite count")
    async def invites(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.author
        
        user_data = await self.db.users.find_one({"user_id": user.id})
        invite_count = user_data.get("invite_count", 0) if user_data else 0
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        invite_points = config["point_rates"]["invite"]
        
        embed = discord.Embed(
            title=f"📨 Invite Stats: {user.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(name="Total Invites", value=f"**{invite_count}**", inline=True)
        embed.add_field(name="Points per Invite", value=f"**{invite_points}**", inline=True)
        
        verified_role = ctx.guild.get_role(self.verified_role_id)
        if verified_role and verified_role in user.roles:
            embed.add_field(name="Status", value="✅ **Verified**", inline=True)
            embed.add_field(name="Points Earned", value=f"**{invite_count * invite_points}**", inline=True)
        else:
            embed.add_field(name="Status", value="❌ **Not Verified**", inline=True)
            embed.add_field(
                name="Pending Points", 
                value=f"**{invite_count * invite_points}**\n*Get <@&{self.verified_role_id}> to claim*", 
                inline=True
            )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(InviteCog(bot))