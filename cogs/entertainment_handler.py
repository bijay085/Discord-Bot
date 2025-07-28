import discord
from discord.ext import commands
import os
import sys
from pathlib import Path
import importlib.util
import traceback
from datetime import datetime, timezone

class EntertainmentHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loaded_modules = []
        self.failed_modules = []
        
    async def cog_load(self):
        print("\n🎮 Loading Entertainment Modules...")
        print("=" * 50)
        
        # Get the root directory (parent of cogs)
        current_file = Path(__file__).resolve()
        cogs_dir = current_file.parent
        root_dir = cogs_dir.parent
        entertainment_dir = root_dir / "entertainment"
        
        # Debug: Print paths
        print(f"📍 Current file: {current_file}")
        print(f"📁 Root directory: {root_dir}")
        print(f"🎮 Looking for entertainment at: {entertainment_dir}")
        
        if not entertainment_dir.exists():
            print(f"❌ Entertainment directory not found!")
            print(f"   Expected location: {entertainment_dir}")
            return
            
        print(f"✅ Entertainment directory found: {entertainment_dir}")
        
        # Add entertainment directory to Python path
        if str(entertainment_dir.parent) not in sys.path:
            sys.path.insert(0, str(entertainment_dir.parent))
        
        # Find all Python files
        python_files = [f for f in entertainment_dir.iterdir() 
                       if f.suffix == '.py' and f.name != '__init__.py']
        
        if not python_files:
            print("❌ No Python files found in entertainment directory!")
            print(f"   Directory contents: {list(entertainment_dir.iterdir())}")
            return
            
        print(f"📋 Found {len(python_files)} module(s) to load:")
        for f in python_files:
            print(f"   - {f.name}")
        
        # Load each module
        for file_path in sorted(python_files):
            module_name = file_path.stem
            print(f"\n🔄 Loading: {module_name}")
            
            try:
                # Remove from sys.modules if already loaded
                full_module_name = f'entertainment.{module_name}'
                if full_module_name in sys.modules:
                    del sys.modules[full_module_name]
                
                # Create module spec
                spec = importlib.util.spec_from_file_location(
                    full_module_name,
                    file_path
                )
                
                if spec and spec.loader:
                    # Load the module
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[full_module_name] = module
                    spec.loader.exec_module(module)
                    
                    # Check for setup function
                    if hasattr(module, 'setup'):
                        await module.setup(self.bot)
                        self.loaded_modules.append(module_name)
                        print(f"  ✅ Successfully loaded: {module_name}")
                    else:
                        print(f"  ⚠️ No setup function in: {module_name}")
                        self.failed_modules.append((module_name, "No setup function"))
                else:
                    print(f"  ❌ Could not create module spec for: {module_name}")
                    self.failed_modules.append((module_name, "Failed to create spec"))
                    
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"  ❌ Failed to load {module_name}: {error_msg}")
                print(f"  📋 Traceback:")
                traceback.print_exc()
                self.failed_modules.append((module_name, error_msg))
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Entertainment Module Summary:")
        print(f"  ✅ Loaded: {len(self.loaded_modules)} module(s)")
        if self.loaded_modules:
            print(f"     {', '.join(self.loaded_modules)}")
        print(f"  ❌ Failed: {len(self.failed_modules)} module(s)")
        if self.failed_modules:
            for name, reason in self.failed_modules:
                print(f"     {name}: {reason}")
        print("=" * 50 + "\n")
    
    @commands.command(name="entertainment", aliases=["ent", "games"])
    @commands.is_owner()
    async def entertainment_status(self, ctx):
        """Check the status of entertainment modules"""
        embed = discord.Embed(
            title="🎮 Entertainment Module Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if self.loaded_modules:
            embed.add_field(
                name=f"✅ Loaded Modules ({len(self.loaded_modules)})",
                value="\n".join([f"• {mod}" for mod in self.loaded_modules]),
                inline=False
            )
        
        if self.failed_modules:
            embed.add_field(
                name=f"❌ Failed Modules ({len(self.failed_modules)})",
                value="\n".join([f"• {name}: {reason[:50]}..." if len(reason) > 50 else f"• {name}: {reason}" 
                                for name, reason in self.failed_modules]),
                inline=False
            )
        
        if not self.loaded_modules and not self.failed_modules:
            embed.add_field(
                name="📦 No Modules",
                value="No entertainment modules found or loaded.",
                inline=False
            )
        
        # Show active cogs
        cogs_list = []
        for cog_name, cog in self.bot.cogs.items():
            if any(mod.lower() in cog_name.lower() for mod in self.loaded_modules):
                cogs_list.append(cog_name)
        
        if cogs_list:
            embed.add_field(
                name="🎯 Active Entertainment Cogs",
                value="\n".join([f"• {cog}" for cog in cogs_list]),
                inline=False
            )
        
        # Add directory info
        root_dir = Path(__file__).resolve().parent.parent
        entertainment_dir = root_dir / "entertainment"
        
        embed.add_field(
            name="📁 Directory Info",
            value=f"Location: `{entertainment_dir}`\nExists: {'✅' if entertainment_dir.exists() else '❌'}",
            inline=False
        )
        
        embed.set_footer(text="Use /bet to try the betting game!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="reload_entertainment", aliases=["reload_ent"])
    @commands.is_owner()
    async def reload_entertainment(self, ctx):
        """Reload all entertainment modules"""
        await ctx.send("🔄 Reloading entertainment modules...")
        
        # Remove existing entertainment cogs
        for module_name in self.loaded_modules[:]:
            try:
                # Find and remove cog
                for name, cog in list(self.bot.cogs.items()):
                    if module_name.lower() in name.lower():
                        await self.bot.remove_cog(name)
                        break
            except:
                pass
        
        # Clear lists
        self.loaded_modules.clear()
        self.failed_modules.clear()
        
        # Reload
        await self.cog_load()
        
        embed = discord.Embed(
            title="✅ Reload Complete",
            description=f"Loaded: {len(self.loaded_modules)} modules\nFailed: {len(self.failed_modules)} modules",
            color=discord.Color.green()
        )
        
        if self.loaded_modules:
            embed.add_field(
                name="Loaded",
                value=", ".join(self.loaded_modules),
                inline=False
            )
            
        await ctx.send(embed=embed)

async def setup(bot):
    """Setup function to add this cog to the bot"""
    await bot.add_cog(EntertainmentHandler(bot))