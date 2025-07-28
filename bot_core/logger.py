import logging
import sys
import discord
import aiohttp
from datetime import datetime, timezone

class WebhookHandler(logging.Handler):
    def __init__(self, webhook_url=None):
        super().__init__()
        self.webhook_url = webhook_url
        self.session = None
        
    async def send_to_webhook(self, record):
        if not self.webhook_url or not self.session:
            return
            
        try:
            webhook = discord.Webhook.from_url(self.webhook_url, session=self.session)
            
            color = {
                'ERROR': 0xFF0000,
                'WARNING': 0xFFA500,
                'CRITICAL': 0x8B0000
            }.get(record.levelname, 0x808080)
            
            embed = discord.Embed(
                title=f"⚠️ {record.levelname}",
                description=f"```{record.getMessage()[:1000]}```",
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            
            if hasattr(record, 'exc_info') and record.exc_info:
                import traceback
                exc_text = ''.join(traceback.format_exception(*record.exc_info))
                embed.add_field(name="Exception", value=f"```{exc_text[:1000]}```", inline=False)
            
            await webhook.send(embed=embed)
        except:
            pass
    
    def emit(self, record):
        if record.levelname in ['ERROR', 'WARNING', 'CRITICAL']:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.send_to_webhook(record))
            except:
                pass

webhook_handler = WebhookHandler()

def setup_logging():
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    logging.basicConfig(
        level=logging.WARNING,
        handlers=[file_handler, webhook_handler],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logging.getLogger('discord').setLevel(logging.ERROR)
    logging.getLogger('discord.client').setLevel(logging.ERROR)
    logging.getLogger('discord.gateway').setLevel(logging.ERROR)
    logging.getLogger('discord.http').setLevel(logging.ERROR)
    
    return logging.getLogger('CookieBot')