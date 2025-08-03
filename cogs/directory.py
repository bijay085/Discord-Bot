# cogs/directory.py
# Location: cogs/directory.py
# Description: Directory monitoring that only alerts on changes to analytics channel

import discord
from discord.ext import commands, tasks
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import json
import hashlib

class DirectoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.stock_cache = {}
        self.last_report_hash = None  # Track last report to detect changes
        self.check_directories.start()
        self.update_stock_cache.start()
        
    async def log_action(self, guild_id: int, message: str, color: discord.Color = discord.Color.blue()):
        cookie_cog = self.bot.get_cog("CookieCog")
        if cookie_cog:
            await cookie_cog.log_action(guild_id, message, color)
    
    async def is_owner(self, user_id: int) -> bool:
        config = await self.db.config.find_one({"_id": "bot_config"})
        return user_id == config.get("owner_id")
    
    async def get_user_role_config(self, member: discord.Member, server: dict) -> dict:
        """Get the best role configuration for a user based on role hierarchy"""
        if not server.get("role_based"):
            return {}
            
        best_config = {}
        highest_priority = -1
        
        for role in member.roles:
            role_config = server["roles"].get(str(role.id))
            if role_config and isinstance(role_config, dict):
                if role.position > highest_priority:
                    highest_priority = role.position
                    best_config = role_config
        
        return best_config
    
    @tasks.loop(minutes=5)
    async def update_stock_cache(self):
        """Update stock cache every 5 minutes for better performance"""
        try:
            self.stock_cache = {}
            
            # Get bot config for default directories
            config = await self.db.config.find_one({"_id": "bot_config"})
            if config and config.get("default_cookies"):
                for cookie_type, cookie_config in config["default_cookies"].items():
                    directory = cookie_config.get("directory")
                    if directory and os.path.exists(directory):
                        self.stock_cache[directory] = len([f for f in os.listdir(directory) if f.endswith('.txt')])
            
            # Update server-specific directories
            async for server in self.db.servers.find({"enabled": True}):
                for cookie_type, config in server.get("cookies", {}).items():
                    directory = config.get("directory")
                    if directory and os.path.exists(directory) and directory not in self.stock_cache:
                        self.stock_cache[directory] = len([f for f in os.listdir(directory) if f.endswith('.txt')])
                        
        except Exception as e:
            print(f"Error updating stock cache: {e}")
    
    @tasks.loop(hours=1)
    async def check_directories(self):
        try:
            config = await self.db.config.find_one({"_id": "bot_config"})
            if not config:
                return
                
            # Prepare report data
            report_data = {
                "missing_dirs": [],
                "critical_stock": [],
                "low_stock": [],
                "medium_stock": [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Check default directories
            if config.get("default_cookies"):
                for cookie_type, cookie_config in config["default_cookies"].items():
                    directory = cookie_config.get("directory")
                    if not directory:
                        continue
                    
                    if not os.path.exists(directory):
                        report_data["missing_dirs"].append(f"{cookie_type} - {directory}")
                        Path(directory).mkdir(parents=True, exist_ok=True)
                    else:
                        files_count = self.stock_cache.get(directory, len([f for f in os.listdir(directory) if f.endswith('.txt')]))
                        
                        if files_count == 0:
                            report_data["critical_stock"].append(f"{cookie_type} - EMPTY")
                        elif files_count < 5:
                            report_data["low_stock"].append(f"{cookie_type} - {files_count} files")
                        elif files_count < 20:
                            report_data["medium_stock"].append(f"{cookie_type} - {files_count} files")
            
            # Check server-specific directories
            async for server in self.db.servers.find({"enabled": True}):
                for cookie_type, cookie_config in server.get("cookies", {}).items():
                    if not cookie_config.get("enabled", True):
                        continue
                        
                    directory = cookie_config.get("directory")
                    if not directory:
                        continue
                    
                    server_name = server.get('server_name', 'Unknown')[:20]
                    
                    if not os.path.exists(directory):
                        report_data["missing_dirs"].append(f"{server_name}: {cookie_type} - {directory}")
                        Path(directory).mkdir(parents=True, exist_ok=True)
                    else:
                        files_count = self.stock_cache.get(directory, len([f for f in os.listdir(directory) if f.endswith('.txt')]))
                        
                        if files_count == 0:
                            report_data["critical_stock"].append(f"{server_name}: {cookie_type} - EMPTY")
                        elif files_count < 5:
                            report_data["low_stock"].append(f"{server_name}: {cookie_type} - {files_count} files")
                        elif files_count < 20:
                            report_data["medium_stock"].append(f"{server_name}: {cookie_type} - {files_count} files")
            
            # Create hash of current report (excluding timestamp)
            report_content = {k: v for k, v in report_data.items() if k != "timestamp"}
            current_hash = hashlib.md5(json.dumps(report_content, sort_keys=True).encode()).hexdigest()
            
            # Check if there are any issues
            has_issues = any([
                report_data["missing_dirs"],
                report_data["critical_stock"],
                report_data["low_stock"]
            ])
            
            # Only send if there are issues AND the report has changed
            if has_issues and current_hash != self.last_report_hash:
                # Find analytics channel in ALL servers
                analytics_sent = False
                
                # First try to find in all enabled servers
                async for server_doc in self.db.servers.find({"enabled": True}):
                    analytics_channel_id = server_doc.get("channels", {}).get("analytics")
                    if analytics_channel_id:
                        channel = self.bot.get_channel(analytics_channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="📁 Directory Status Report",
                                description=f"Stock check performed at <t:{int(datetime.now(timezone.utc).timestamp())}:F>",
                                color=discord.Color.red() if report_data["critical_stock"] else discord.Color.orange(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            
                            if report_data["critical_stock"]:
                                embed.add_field(
                                    name="🚨 CRITICAL - Empty Directories",
                                    value="\n".join(report_data["critical_stock"][:10]) or "None",
                                    inline=False
                                )
                            
                            if report_data["missing_dirs"]:
                                embed.add_field(
                                    name="❌ Missing Directories (Auto-Created)",
                                    value="\n".join(report_data["missing_dirs"][:10]) or "None",
                                    inline=False
                                )
                            
                            if report_data["low_stock"]:
                                embed.add_field(
                                    name="⚠️ Low Stock Warning",
                                    value="\n".join(report_data["low_stock"][:10]) or "None",
                                    inline=False
                                )
                            
                            # Add summary
                            total_issues = len(report_data["critical_stock"]) + len(report_data["low_stock"]) + len(report_data["missing_dirs"])
                            embed.add_field(
                                name="📊 Summary",
                                value=f"Total Issues: **{total_issues}**\nNext check: <t:{int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}:R>",
                                inline=False
                            )
                            
                            embed.set_footer(text="Automated Directory Monitor • Only sends on changes")
                            
                            await channel.send(embed=embed)
                            analytics_sent = True
                            
                            # Store this report hash
                            self.last_report_hash = current_hash
                            
                            # Save last report to database for persistence
                            await self.db.config.update_one(
                                {"_id": "directory_monitor"},
                                {
                                    "$set": {
                                        "last_report_hash": current_hash,
                                        "last_report_time": datetime.now(timezone.utc),
                                        "last_report_data": report_data
                                    }
                                },
                                upsert=True
                            )
                            
                            print(f"📊 Directory report sent to analytics channel in {server_doc.get('server_name', 'Unknown')}")
                            break  # Only send to first analytics channel found
                
                if not analytics_sent:
                    print("⚠️ No analytics channel found in any server!")
                    
            elif has_issues and current_hash == self.last_report_hash:
                print("📁 Directory check: No changes detected, skipping notification")
            elif not has_issues:
                print("✅ Directory check: All directories healthy!")
                # Reset hash when all issues are resolved
                if self.last_report_hash is not None:
                    self.last_report_hash = None
                    await self.db.config.update_one(
                        {"_id": "directory_monitor"},
                        {"$set": {"last_report_hash": None}}
                    )
                        
        except Exception as e:
            print(f"Error in directory check: {e}")
    
    @update_stock_cache.before_loop
    async def before_update_stock_cache(self):
        await self.bot.wait_until_ready()
    
    @check_directories.before_loop
    async def before_check_directories(self):
        await self.bot.wait_until_ready()
        
        # Load last report hash from database
        monitor_data = await self.db.config.find_one({"_id": "directory_monitor"})
        if monitor_data:
            self.last_report_hash = monitor_data.get("last_report_hash")
            print(f"📁 Loaded previous directory report hash: {self.last_report_hash}")
    
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
        total_stock = 0
        
        # Check default directories first
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("default_cookies"):
            default_status = []
            for cookie_type, cookie_config in config["default_cookies"].items():
                directory = cookie_config.get("directory")
                if not directory:
                    continue
                
                checked += 1
                
                if not os.path.exists(directory):
                    default_status.append(f"❌ {cookie_type}: Missing")
                    all_good = False
                else:
                    files_count = self.stock_cache.get(directory)
                    if files_count is None:
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        files_count = len(files)
                        self.stock_cache[directory] = files_count
                    
                    total_stock += files_count
                    
                    if files_count == 0:
                        default_status.append(f"🔴 {cookie_type}: Empty")
                        all_good = False
                    elif files_count < 5:
                        default_status.append(f"🟡 {cookie_type}: Low ({files_count} files)")
                    else:
                        default_status.append(f"🟢 {cookie_type}: OK ({files_count} files)")
            
            if default_status:
                embed.add_field(
                    name="📋 Default Directories",
                    value="\n".join(default_status[:10]),
                    inline=False
                )
        
        # Check server-specific directories
        server_count = 0
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
                    files_count = self.stock_cache.get(directory)
                    if files_count is None:
                        files = [f for f in os.listdir(directory) if f.endswith('.txt')]
                        files_count = len(files)
                        self.stock_cache[directory] = files_count
                    
                    total_stock += files_count
                    
                    if files_count == 0:
                        server_status.append(f"🔴 {cookie_type}: Empty")
                        all_good = False
                    elif files_count < 5:
                        server_status.append(f"🟡 {cookie_type}: Low ({files_count} files)")
                    else:
                        server_status.append(f"🟢 {cookie_type}: OK ({files_count} files)")
            
            if server_status and server_count < 5:  # Limit to first 5 servers
                embed.add_field(
                    name=f"{server_name[:50]}",
                    value="\n".join(server_status[:5]),
                    inline=False
                )
                server_count += 1
        
        embed.description = f"Checked **{checked}** directories | Total Stock: **{total_stock}** files\nStatus: {'✅ All directories OK' if all_good else '⚠️ Issues found'}"
        
        # Add info about automated monitoring
        monitor_data = await self.db.config.find_one({"_id": "directory_monitor"})
        if monitor_data and monitor_data.get("last_report_time"):
            last_check = monitor_data["last_report_time"]
            embed.add_field(
                name="🤖 Automated Monitoring",
                value=f"Last check: <t:{int(last_check.timestamp())}:R>\nNext check: <t:{int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}:R>",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
        await self.log_action(
            ctx.guild.id,
            f"📁 {ctx.author.mention} performed manual directory check",
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
        
        # Create default directories
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("default_cookies"):
            for cookie_type, cookie_config in config["default_cookies"].items():
                directory = cookie_config.get("directory")
                if not directory:
                    continue
                
                if not os.path.exists(directory):
                    try:
                        Path(directory).mkdir(parents=True, exist_ok=True)
                        # Create README file
                        readme_path = Path(directory) / "README.txt"
                        if not readme_path.exists():
                            readme_content = f"""Cookie Directory: {cookie_type.upper()}
=================================
Place .txt files containing cookies here.
Each file should contain one cookie per line.

Format examples:
- email:password
- username:password
- token
- session_id

Files will be randomly selected and distributed.
Category: {cookie_config.get('category', 'general')}
"""
                            readme_path.write_text(readme_content)
                        created += 1
                    except Exception as e:
                        failed += 1
                        print(f"Failed to create {directory}: {e}")
        
        # Create server-specific directories
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
        
        # Update cache after creating directories
        await self.update_stock_cache()
        
        await self.log_action(
            ctx.guild.id,
            f"📁 {ctx.author.mention} created {created} missing directories",
            discord.Color.green()
        )
    
    @commands.hybrid_command(name="forcedircheck", description="Force directory check now (Owner only)")
    async def forcedircheck(self, ctx):
        if not await self.is_owner(ctx.author.id):
            await ctx.send("❌ This command is owner only!", ephemeral=True)
            return
        
        await ctx.defer()
        
        # Temporarily clear the hash to force a report
        old_hash = self.last_report_hash
        self.last_report_hash = None
        
        # Run the check
        await self.check_directories()
        
        # Restore if no issues were found
        if self.last_report_hash is None:
            self.last_report_hash = old_hash
        
        embed = discord.Embed(
            title="✅ Directory Check Forced",
            description="Manual directory check completed. Check analytics channel for report if there were changes.",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
    
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
        
        # Validate directory path
        directory = os.path.abspath(directory)
        
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
            # Update cache
            self.stock_cache[directory] = files
        
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
        
        # Get default directories
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config and config.get("default_cookies"):
            for cookie_type, cookie_config in config["default_cookies"].items():
                directory = cookie_config.get("directory")
                if directory:
                    all_dirs.add(directory)
                    if directory not in dir_info:
                        dir_info[directory] = []
                    dir_info[directory].append(f"Default: {cookie_type}")
        
        # Get server directories
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
            files = self.stock_cache.get(directory, len([f for f in os.listdir(directory) if f.endswith('.txt')]) if exists else 0)
            
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

async def setup(bot):
    await bot.add_cog(DirectoryCog(bot))