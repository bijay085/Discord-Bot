import discord
from discord.ext import commands
import os
import sys
from pathlib import Path
import importlib.util
import traceback

class EntertainmentHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loaded_modules = []
        self.failed_modules = []
        
    async def cog_load(self):
        entertainment_dir = Path(__file__).parent.parent / "entertainment"
        
        if not entertainment_dir.exists():
            return
        
        sys.path.insert(0, str(entertainment_dir.parent))
        
        python_files = [f for f in entertainment_dir.iterdir() 
                       if f.suffix == '.py' and f.name != '__init__.py']
        
        if not python_files:
            return
        
        for file_path in sorted(python_files):
            module_name = file_path.stem
            
            try:
                spec = importlib.util.spec_from_file_location(
                    f'entertainment.{module_name}',
                    file_path
                )
                
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, 'setup'):
                        await module.setup(self.bot)
                        self.loaded_modules.append(module_name)
                        print(f"🎮 Entertainment: {module_name} loaded")
                    
            except Exception as e:
                self.failed_modules.append(module_name)
    
    @commands.command(name="entertainment", aliases=["ent"])
    @commands.is_owner()
    async def entertainment_status(self, ctx):
        embed = discord.Embed(
            title="🎮 Entertainment Status",
            color=discord.Color.blue()
        )
        
        if self.loaded_modules:
            embed.add_field(
                name=f"✅ Loaded ({len(self.loaded_modules)})",
                value=", ".join(self.loaded_modules),
                inline=False
            )
        
        if self.failed_modules:
            embed.add_field(
                name=f"❌ Failed ({len(self.failed_modules)})",
                value=", ".join(self.failed_modules),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="reload_ent")
    @commands.is_owner()
    async def reload_entertainment(self, ctx):
        msg = await ctx.send("🔄 Reloading...")
        
        for module_name in self.loaded_modules[:]:
            for name, cog in list(self.bot.cogs.items()):
                if module_name.lower() in name.lower():
                    await self.bot.remove_cog(name)
                    break
        
        self.loaded_modules.clear()
        self.failed_modules.clear()
        
        await self.cog_load()
        
        await msg.edit(content=f"✅ Reloaded: {len(self.loaded_modules)} modules")
    
    @commands.command(name="sync")
    @commands.is_owner()
    async def sync_commands(self, ctx):
        msg = await ctx.send("🔄 Syncing...")
        try:
            synced = await self.bot.tree.sync()
            await msg.edit(content=f"✅ Synced {len(synced)} commands")
        except Exception as e:
            await msg.edit(content=f"❌ Failed: {str(e)[:100]}")

async def setup(bot):
    await bot.add_cog(EntertainmentHandler(bot))