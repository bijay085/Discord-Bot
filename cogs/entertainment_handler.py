# cogs/entertainment_handler.py
# Location: cogs/entertainment_handler.py
# Description: Main handler that loads all entertainment cogs automatically

import os
import importlib
from pathlib import Path
import discord
from discord.ext import commands

class EntertainmentHandler(commands.Cog):
    """Main handler for all entertainment modules"""
    
    def __init__(self, bot):
        self.bot = bot
        self.loaded_cogs = []
        
    async def cog_load(self):
        """Load all entertainment cogs when this handler is loaded"""
        entertainment_dir = Path(__file__).parent / "entertainment"
        
        if not entertainment_dir.exists():
            print("❌ Entertainment folder not found!")
            return
            
        loaded_count = 0
        failed_count = 0
        
        # List all Python files in the entertainment folder
        for filename in sorted(os.listdir(entertainment_dir)):
            # Skip __init__.py and non-python files
            if filename.endswith('.py') and filename != '__init__.py':
                module_name = filename[:-3]
                
                try:
                    # Import the module
                    module_path = f'cogs.entertainment.{module_name}'
                    module = importlib.import_module(module_path)
                    
                    # Load the cog if it has a setup function
                    if hasattr(module, 'setup'):
                        await module.setup(self.bot)
                        self.loaded_cogs.append(module_name)
                        loaded_count += 1
                        print(f"  ✅ Loaded: {module_name}")
                    else:
                        print(f"  ⚠️ No setup function in {module_name}")
                        
                except Exception as e:
                    failed_count += 1
                    print(f"  ❌ Failed to load {module_name}: {e}")
        
        print(f"\n📦 Entertainment Module Summary:")
        print(f"  ✅ Loaded: {loaded_count} cogs")
        print(f"  ❌ Failed: {failed_count} cogs")
        print(f"  📋 Active: {', '.join(self.loaded_cogs)}")
    
    @commands.command(name="entertainment", hidden=True)
    @commands.is_owner()
    async def entertainment_status(self, ctx):
        """Check status of entertainment modules (Owner only)"""
        embed = discord.Embed(
            title="🎮 Entertainment Module Status",
            color=discord.Color.blue()
        )
        
        if self.loaded_cogs:
            embed.add_field(
                name="✅ Loaded Cogs",
                value="\n".join([f"• {cog}" for cog in self.loaded_cogs]),
                inline=False
            )
        else:
            embed.add_field(
                name="❌ No Cogs Loaded",
                value="No entertainment cogs are currently loaded.",
                inline=False
            )
        
        # Check for available cogs
        entertainment_dir = Path(__file__).parent / "entertainment"
        if entertainment_dir.exists():
            available = []
            for filename in os.listdir(entertainment_dir):
                if filename.endswith('.py') and filename != '__init__.py':
                    module_name = filename[:-3]
                    if module_name not in self.loaded_cogs:
                        available.append(module_name)
            
            if available:
                embed.add_field(
                    name="📦 Available but not loaded",
                    value="\n".join([f"• {cog}" for cog in available]),
                    inline=False
                )
        
        await ctx.send(embed=embed)

async def setup(bot):
    """Setup function for the entertainment handler"""
    print("\n🎮 Loading Entertainment Module...")
    await bot.add_cog(EntertainmentHandler(bot))