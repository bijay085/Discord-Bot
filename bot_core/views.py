# bot_core/views.py
# Location: bot_core/views.py
# Description: Bot control views with improved timeout handling

import discord
from datetime import datetime, timezone
import psutil
import platform

class BotControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.response = None
        
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if self.response:
                await self.response.edit(view=self)
        except discord.NotFound:
            pass
        
    @discord.ui.button(label="System Status", style=discord.ButtonStyle.primary, emoji="📊")
    async def system_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        embed = discord.Embed(
            title="🖥️ System Status",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="CPU Usage", value=f"{cpu_percent}%", inline=True)
        embed.add_field(name="RAM Usage", value=f"{memory.percent}%", inline=True)
        embed.add_field(name="Disk Usage", value=f"{disk.percent}%", inline=True)
        embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="Discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Platform", value=platform.system(), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Bot Stats", style=discord.ButtonStyle.success, emoji="📈")
    async def bot_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_users = sum(g.member_count for g in self.bot.guilds)
        total_claims = await self.bot.db.statistics.find_one({"_id": "global_stats"})
        
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(name="Users", value=f"{total_users:,}", inline=True)
        embed.add_field(name="Channels", value=f"{sum(len(g.channels) for g in self.bot.guilds):,}", inline=True)
        
        if total_claims:
            embed.add_field(
                name="Total Claims", 
                value=f"{total_claims.get('all_time_claims', 0):,}", 
                inline=True
            )
        
        embed.add_field(name="Uptime", value=self.bot.get_uptime(), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.edit_original_response(embed=self.create_status_embed())
    
    def get_uptime(self):
        delta = datetime.now(timezone.utc) - self.bot.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
            
        return " ".join(parts)
    
    def create_status_embed(self):
        status_emoji = "🟢" if self.bot.ws else "🔴"
        embed = discord.Embed(
            title=f"{status_emoji} Cookie Bot Status",
            description="Bot is fully operational and ready to serve cookies!",
            color=discord.Color.green() if self.bot.ws else discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Status", value="Online" if self.bot.ws else "Offline", inline=True)
        embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
        embed.add_field(name="Version", value="v2.0.0", inline=True)
        embed.set_footer(text="Cookie Bot Premium", icon_url=self.bot.user.avatar.url if self.bot.user else None)
        return embed