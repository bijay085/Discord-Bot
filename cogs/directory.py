# cogs/directory.py

import discord
from discord.ext import commands, tasks
import os
from pathlib import Path
from datetime import datetime, timezone

class DirectoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_directories.start()
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    @tasks.loop(hours=1)
    async def check_directories(self):
        try:
            config = await self.db.config.find_one({"_id": "bot_config"})
            if not config:
                return
                
            missing_dirs = []
            low_stock = []
            
            async for server in self.db.servers.find({"enabled": True}):
                for cookie_type, cookie_config in server.get("cookies", {}).items():
                    if not cookie_config.get("enabled", True):
                        continue
                        
                    directory = cookie_config.get("directory")
                    if not directory:
                        continue
                    
                    if not os.path.exists(directory):
                        missing_dirs.append(f"{server['server_name']}: {cookie_type} - {directory}")
                        Path(directory).mkdir(parents=True, exist_ok=True)
                    else:
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        if len(files) < 5:
                            low_stock.append(f"{server['server_name']}: {cookie_type} - {len(files)} files")
            
            if missing_dirs or low_stock:
                main_log = config.get("main_log_channel")
                if main_log:
                    channel = self.bot.get_channel(main_log)
                    if channel:
                        embed = discord.Embed(
                            title="📁 Directory Check Report",
                            color=discord.Color.orange(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        if missing_dirs:
                            embed.add_field(
                                name="❌ Missing Directories (Created)",
                                value="\n".join(missing_dirs[:10]) or "None",
                                inline=False
                            )
                        
                        if low_stock:
                            embed.add_field(
                                name="⚠️ Low Stock Warning",
                                value="\n".join(low_stock[:10]) or "None",
                                inline=False
                            )
                        
                        await channel.send(embed=embed)
                        
        except Exception as e:
            print(f"Error in directory check: {e}")
    
    @commands.hybrid_command(name="checkdirs", description="Check all cookie directories (Owner only)")
    async def checkdirs(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        embed = discord.Embed(
            title="📁 Directory Status Check",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        all_good = True
        checked = 0
        
        async for server in self.db.servers.find():
            server_status = []
            server_name = server.get("server_name", "Unknown")
            
            for cookie_type, cookie_config in server.get("cookies", {}).items():
                directory = cookie_config.get("directory")
                if not directory:
                    continue
                
                checked += 1
                
                if not os.path.exists(directory):
                    server_status.append(f"❌ {cookie_type}: Missing")
                    all_good = False
                else:
                    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                    count = len(files)
                    if count == 0:
                        server_status.append(f"🔴 {cookie_type}: Empty")
                        all_good = False
                    elif count < 5:
                        server_status.append(f"🟡 {cookie_type}: Low ({count} files)")
                    else:
                        server_status.append(f"🟢 {cookie_type}: OK ({count} files)")
            
            if server_status and len(embed.fields) < 20:
                embed.add_field(
                    name=f"{server_name[:50]}",
                    value="\n".join(server_status[:5]),
                    inline=False
                )
        
        embed.description = f"Checked **{checked}** directories\nStatus: {'✅ All directories OK' if all_good else '⚠️ Issues found'}"
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"📁 {ctx.author.mention} performed directory check",
            discord.Color.blue()
        )
    
    @commands.hybrid_command(name="createdirs", description="Create missing directories (Owner only)")
    async def createdirs(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        created = 0
        failed = 0
        
        async for server in self.db.servers.find():
            for cookie_type, cookie_config in server.get("cookies", {}).items():
                directory = cookie_config.get("directory")
                if not directory:
                    continue
                
                if not os.path.exists(directory):
                    try:
                        Path(directory).mkdir(parents=True, exist_ok=True)
                        created += 1
                    except Exception as e:
                        failed += 1
                        print(f"Failed to create {directory}: {e}")
        
        embed = discord.Embed(
            title="📁 Directory Creation Complete",
            description=f"Created: **{created}** directories\nFailed: **{failed}**",
            color=discord.Color.green() if failed == 0 else discord.Color.orange()
        )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"📁 {ctx.author.mention} created {created} missing directories",
            discord.Color.green()
        )
    
    @commands.hybrid_command(name="setdir", description="Set cookie directory (Owner only)")
    async def setdir(self, ctx, server_id: str, cookie_type: str, *, directory: str):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        try:
            server_id = int(server_id)
        except:
            await ctx.send("❌ Invalid server ID!", ephemeral=True)
            return
        
        server = await self.db.servers.find_one({"server_id": server_id})
        if not server:
            await ctx.send("❌ Server not found!", ephemeral=True)
            return
        
        cookie_type = cookie_type.lower()
        if cookie_type not in server.get("cookies", {}):
            await ctx.send(f"❌ Cookie type '{cookie_type}' not found!", ephemeral=True)
            return
        
        await self.db.servers.update_one(
            {"server_id": server_id},
            {"$set": {f"cookies.{cookie_type}.directory": directory}}
        )
        
        if not os.path.exists(directory):
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
                status = "✅ Created"
            except:
                status = "⚠️ Could not create"
        else:
            files = len([f for f in os.listdir(directory) if f.endswith('.txt')])
            status = f"✅ Exists ({files} files)"
        
        embed = discord.Embed(
            title="📁 Directory Updated",
            color=discord.Color.green()
        )
        embed.add_field(name="Server", value=server.get("server_name", "Unknown"), inline=True)
        embed.add_field(name="Cookie Type", value=cookie_type, inline=True)
        embed.add_field(name="Directory", value=f"`{directory}`", inline=False)
        embed.add_field(name="Status", value=status, inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="listdirs", description="List all directories (Owner only)")
    async def listdirs(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        all_dirs = set()
        dir_info = {}
        
        async for server in self.db.servers.find():
            for cookie_type, cookie_config in server.get("cookies", {}).items():
                directory = cookie_config.get("directory")
                if directory:
                    all_dirs.add(directory)
                    if directory not in dir_info:
                        dir_info[directory] = []
                    dir_info[directory].append(f"{server.get('server_name', 'Unknown')}: {cookie_type}")
        
        embed = discord.Embed(
            title="📁 All Cookie Directories",
            description=f"Total unique directories: **{len(all_dirs)}**",
            color=discord.Color.blue()
        )
        
        for directory in sorted(all_dirs)[:20]:
            exists = os.path.exists(directory)
            files = len([f for f in os.listdir(directory) if f.endswith('.txt')]) if exists else 0
            
            value = f"{'✅' if exists else '❌'} Files: **{files}**\nUsed by: {', '.join(dir_info[directory][:3])}"
            if len(dir_info[directory]) > 3:
                value += f" +{len(dir_info[directory]) - 3} more"
            
            embed.add_field(
                name=f"`{directory[-50:]}`" if len(directory) > 50 else f"`{directory}`",
                value=value,
                inline=False
            )
        
        if len(all_dirs) > 20:
            embed.set_footer(text=f"Showing first 20 of {len(all_dirs)} directories")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="syncstock", description="Sync stock across servers with same directories (Owner only)")
    async def syncstock(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        dir_to_servers = {}
        
        async for server in self.db.servers.find():
            for cookie_type, cookie_config in server.get("cookies", {}).items():
                directory = cookie_config.get("directory")
                if directory:
                    if directory not in dir_to_servers:
                        dir_to_servers[directory] = []
                    dir_to_servers[directory].append({
                        "server_id": server["server_id"],
                        "server_name": server.get("server_name", "Unknown"),
                        "cookie_type": cookie_type
                    })
        
        embed = discord.Embed(
            title="📁 Directory Sync Report",
            description="Servers sharing the same directories:",
            color=discord.Color.blue()
        )
        
        shared_count = 0
        for directory, servers in dir_to_servers.items():
            if len(servers) > 1:
                shared_count += 1
                if len(embed.fields) < 10:
                    server_list = "\n".join([f"• {s['server_name']}: {s['cookie_type']}" for s in servers[:5]])
                    if len(servers) > 5:
                        server_list += f"\n• +{len(servers) - 5} more"
                    
                    embed.add_field(
                        name=f"Directory: `{directory[-40:]}`" if len(directory) > 40 else f"Directory: `{directory}`",
                        value=server_list,
                        inline=False
                    )
        
        embed.description += f"\n\nFound **{shared_count}** shared directories"
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DirectoryCog(bot))