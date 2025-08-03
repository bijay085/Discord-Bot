# cogs/givecookie.py
# Location: cogs/givecookie.py
# Description: Simple owner-only command to give cookies directly to users

import discord
from discord.ext import commands
from discord import app_commands
import os
import random
from datetime import datetime, timezone
import traceback
from typing import List
from dotenv import load_dotenv

load_dotenv('setup/.env')

class GiveCookieCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.owner_id = int(os.getenv("OWNER_ID", "1192694890530869369"))
    
    async def cookie_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for cookie types"""
        # Get cookie configs from database
        config = await self.db.config.find_one({"_id": "bot_config"})
        if not config or "default_cookies" not in config:
            return []
        
        choices = []
        for cookie_type, cookie_config in config["default_cookies"].items():
            if cookie_type.lower().startswith(current.lower()):
                directory = cookie_config["directory"]
                stock = 0
                if os.path.exists(directory):
                    stock = len([f for f in os.listdir(directory) if f.endswith('.txt')])
                
                emoji = cookie_config.get("emoji", "🍪")
                status = f"Stock: {stock}" if stock > 0 else "Out of Stock"
                
                choices.append(app_commands.Choice(
                    name=f"{emoji} {cookie_type} - {status}",
                    value=cookie_type
                ))
        
        return choices[:25]
    
    @commands.hybrid_command(name="givecookie", description="Give a cookie to a user (Owner only)")
    @app_commands.describe(
        user="The user to give the cookie to",
        type="The type of cookie to give"
    )
    @app_commands.autocomplete(type=cookie_autocomplete)
    async def givecookie(self, ctx, user: discord.User, type: str):
        try:
            # Check if user is THE bot owner (not server owner)
            if ctx.author.id != self.owner_id:
                embed = discord.Embed(
                    title="🔒 Access Denied",
                    description="This command is restricted to the bot owner only!",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Your ID: {ctx.author.id} | Required: {self.owner_id}")
                await ctx.send(embed=embed, ephemeral=True)
                return
            
            # Defer the response
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.interaction.response.defer(ephemeral=True)
            
            # Get cookie directories from database
            config = await self.db.config.find_one({"_id": "bot_config"})
            if not config or "default_cookies" not in config:
                await ctx.send("❌ Cookie configuration not found!", ephemeral=True)
                return
            
            cookie_type = type.lower()
            if cookie_type not in config["default_cookies"]:
                await ctx.send(f"❌ Invalid cookie type: **{type}**", ephemeral=True)
                return
            
            cookie_config = config["default_cookies"][cookie_type]
            directory = cookie_config["directory"]
            
            # Check if directory exists and has files
            if not os.path.exists(directory):
                await ctx.send(f"❌ Directory for **{cookie_type}** not found!", ephemeral=True)
                return
            
            files = [f for f in os.listdir(directory) if f.endswith('.txt')]
            if not files:
                await ctx.send(f"❌ No **{cookie_type}** cookies available!", ephemeral=True)
                return
            
            # Select random file
            selected_file = random.choice(files)
            file_path = os.path.join(directory, selected_file)
            
            # Prepare the cookie embed for DM
            cookie_embed = discord.Embed(
                title=f"🎁 {cookie_type.upper()} Cookie Gift!",
                description=f"You received a **{cookie_type}** cookie from the bot owner!",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc)
            )
            
            cookie_embed.add_field(name="📁 File", value=f"`{selected_file}`", inline=True)
            cookie_embed.add_field(name="💰 Cost", value="**FREE** (Owner Gift)", inline=True)
            cookie_embed.add_field(name="🎉 Type", value=cookie_type.title(), inline=True)
            
            cookie_embed.add_field(
                name="💡 Note",
                value="This is a special gift from the bot owner. No feedback required!",
                inline=False
            )
            
            cookie_embed.set_footer(text="Enjoy your cookie! 🍪 • No points deducted")
            
            # Try to send the cookie via DM
            try:
                await user.send(embed=cookie_embed, file=discord.File(file_path))
                
                # Success response
                success_embed = discord.Embed(
                    title="✅ Cookie Delivered!",
                    description=f"Successfully sent a **{cookie_type}** cookie to {user.mention}!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                success_embed.add_field(name="📁 File", value=f"`{selected_file}`", inline=True)
                success_embed.add_field(name="📨 Delivered To", value=user.mention, inline=True)
                success_embed.add_field(name="💰 Cost", value="Free (No points deducted)", inline=True)
                success_embed.set_footer(text="Cookie sent via DM")
                
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send(embed=success_embed, ephemeral=True)
                else:
                    await ctx.send(embed=success_embed, ephemeral=True)
                    
            except discord.Forbidden:
                # DM failed
                error_embed = discord.Embed(
                    title="❌ DM Delivery Failed",
                    description=f"Could not send DM to {user.mention}!",
                    color=discord.Color.red()
                )
                error_embed.add_field(
                    name="Possible Reasons",
                    value="• User has DMs disabled\n• User blocked the bot\n• Privacy settings",
                    inline=False
                )
                
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send(embed=error_embed, ephemeral=True)
                else:
                    await ctx.send(embed=error_embed, ephemeral=True)
                    
        except Exception as e:
            print(f"Error in givecookie command: {traceback.format_exc()}")
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.interaction.followup.send(embed=error_embed, ephemeral=True)
                else:
                    await ctx.send(embed=error_embed, ephemeral=True)
            except:
                pass

async def setup(bot):
    await bot.add_cog(GiveCookieCog(bot))