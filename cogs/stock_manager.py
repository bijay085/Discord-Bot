import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timezone
from typing import List
from database_operations import DatabaseOperations
from role_manager import RoleManager

class StockManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.db_ops = DatabaseOperations(bot.db)
        self.role_manager = RoleManager()
    
    async def cookie_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        server = await self.db.servers.find_one({"server_id": interaction.guild_id})
        if not server:
            return []
        
        user_data = await self.db_ops.get_or_create_user(interaction.user.id, str(interaction.user))
        
        choices = []
        for cookie_type, config in server.get("cookies", {}).items():
            if config.get("enabled", True) and cookie_type.lower().startswith(current.lower()):
                access = await self.role_manager.get_user_cookie_access(interaction.user, server, cookie_type, self.db)
                if access.get("enabled", False):
                    cost = access.get("cost", config["cost"])
                    can_afford = user_data["points"] >= cost
                    
                    daily_limit = access.get("daily_limit", -1)
                    can_claim, claimed = await self.db_ops.check_daily_limit(interaction.user.id, cookie_type, daily_limit)
                    
                    if not can_claim:
                        emoji = "🚫"
                        status = f"Daily limit reached ({claimed}/{daily_limit})"
                    else:
                        emoji = "✅" if can_afford else "❌"
                        status = f"{cost} points"
                        if daily_limit != -1:
                            status += f" ({claimed}/{daily_limit} today)"
                    
                    choices.append(app_commands.Choice(
                        name=f"{emoji} {cookie_type} - {status}",
                        value=cookie_type
                    ))
        
        return choices[:25]
    
    @commands.hybrid_command(name="stock", description="Check cookie stock with beautiful display")
    @app_commands.describe(type="The type of cookie to check stock for (leave empty for all)")
    @app_commands.autocomplete(type=cookie_autocomplete)
    async def stock(self, ctx, type: str = None):
        try:
            interaction = ctx.interaction
            if interaction and not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            server = await self.db.servers.find_one({"server_id": ctx.guild.id})
            if not server:
                await ctx.send("❌ Server not configured!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 Cookie Stock Manager",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            role_config = await self.role_manager.get_user_role_config(ctx.author, server, self.db)
            if role_config:
                embed.description = f"Viewing with **{role_config.get('name', 'Default')}** role benefits"
            
            total_stock = 0
            stock_data = []
            
            if type:
                type = type.lower()
                if type not in server["cookies"]:
                    await ctx.send("❌ Invalid cookie type!", ephemeral=True)
                    return
                    
                cookie_config = server["cookies"][type]
                directory = cookie_config["directory"]
                
                access = await self.role_manager.get_user_cookie_access(ctx.author, server, type, self.db)
                
                if not access.get("enabled", False):
                    embed = discord.Embed(
                        title="❌ Access Denied",
                        description=f"Your role doesn't have access to **{type}** cookies!",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed, ephemeral=True)
                    return
                
                cost = access.get("cost", cookie_config["cost"])
                cooldown = access.get("cooldown", cookie_config["cooldown"])
                daily_limit = access.get("daily_limit", -1)
                
                can_claim, claimed_today = await self.db_ops.check_daily_limit(ctx.author.id, type, daily_limit)
                
                if os.path.exists(directory):
                    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                    count = len(files)
                    
                    if count > 20:
                        status = "✅ Well Stocked"
                        color = discord.Color.green()
                    elif count > 10:
                        status = "🟨 Medium Stock"
                        color = discord.Color.gold()
                    elif count > 0:
                        status = "⚠️ Low Stock"
                        color = discord.Color.orange()
                    else:
                        status = "❌ Out of Stock"
                        color = discord.Color.red()
                    
                    embed.color = color
                    embed.add_field(
                        name=f"🍪 {type.title()} Cookie",
                        value=f"**Stock:** {count} files\n**Status:** {status}\n**Your Cost:** {cost} points\n**Your Cooldown:** {cooldown} hours",
                        inline=False
                    )
                    
                    if daily_limit != -1:
                        embed.add_field(
                            name="📅 Daily Limit",
                            value=f"**{claimed_today}/{daily_limit}** claimed today\n{'✅ Can claim' if can_claim else '❌ Limit reached'}",
                            inline=True
                        )
                    
                    progress = min(count / 50 * 100, 100)
                    bar_length = 20
                    filled = int(progress / 100 * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    embed.add_field(
                        name="Stock Level",
                        value=f"{bar} {progress:.0f}%",
                        inline=False
                    )
                else:
                    embed.add_field(name=type.title(), value="❌ Directory not found", inline=False)
            else:
                accessible_cookies = 0
                
                for cookie_type, cookie_config in server["cookies"].items():
                    if not cookie_config.get("enabled", True):
                        continue
                    
                    access = await self.role_manager.get_user_cookie_access(ctx.author, server, cookie_type, self.db)
                    if not access.get("enabled", False):
                        continue
                        
                    accessible_cookies += 1
                    directory = cookie_config["directory"]
                    
                    if os.path.exists(directory):
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        count = len(files)
                        total_stock += count
                        
                        cost = access.get("cost", cookie_config["cost"])
                        daily_limit = access.get("daily_limit", -1)
                        can_claim, claimed_today = await self.db_ops.check_daily_limit(ctx.author.id, cookie_type, daily_limit)
                        
                        if count > 20:
                            emoji = "🟢"
                        elif count > 10:
                            emoji = "🟡"
                        elif count > 0:
                            emoji = "🟠"
                        else:
                            emoji = "🔴"
                        
                        if not can_claim:
                            emoji = "🚫"
                        
                        stock_data.append((cookie_type, count, emoji, cost, daily_limit, claimed_today))
                
                stock_data.sort(key=lambda x: x[1], reverse=True)
                
                for cookie_type, count, emoji, cost, limit, claimed in stock_data[:10]:
                    field_value = f"**{count}** files\n{cost} points"
                    if limit != -1:
                        field_value += f"\n{claimed}/{limit} today"
                    
                    embed.add_field(
                        name=f"{emoji} {cookie_type.title()}",
                        value=field_value,
                        inline=True
                    )
                
                if accessible_cookies == 0:
                    embed.add_field(
                        name="❌ No Access",
                        value="Your role doesn't have access to any cookies!",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📊 Summary",
                        value=f"**{accessible_cookies}** accessible types\n**{total_stock}** total files",
                        inline=False
                    )
                
                if total_stock > 100:
                    health = "🟢 Excellent"
                elif total_stock > 50:
                    health = "🟡 Good"
                elif total_stock > 20:
                    health = "🟠 Fair"
                else:
                    health = "🔴 Critical"
                
                embed.set_footer(text=f"Total Stock: {total_stock} files | Health: {health}")
            
            if interaction and interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in stock command: {e}")
            try:
                await ctx.send("❌ An error occurred!", ephemeral=True)
            except:
                pass

async def setup(bot):
    await bot.add_cog(StockManager(bot))