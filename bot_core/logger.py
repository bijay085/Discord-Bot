# bot_core/logger.py
import logging
import sys
import discord
import aiohttp
import asyncio
from datetime import datetime, timezone
from collections import deque

class WebhookHandler(logging.Handler):
    def __init__(self, webhook_url=None):
        super().__init__()
        self.webhook_url = webhook_url
        self.session = None
        self.queue = asyncio.Queue(maxsize=100)
        self.last_sent = {}
        self.rate_limit_window = 60
        self.max_messages_per_window = 10
        self.error_counts = {}
        self.ignored_errors = [
            "SSL handshake failed",
            "10054",
            "10053",
            "An existing connection was forcibly closed",
            "AutoReconnect"
        ]
        
    async def send_to_webhook(self, record):
        if not self.webhook_url or not self.session:
            return
        
        # Filter out known MongoDB connection errors
        message = record.getMessage()
        for ignored in self.ignored_errors:
            if ignored in message:
                return
        
        try:
            # Rate limiting check
            current_time = datetime.now().timestamp()
            window_start = current_time - self.rate_limit_window
            
            self.last_sent = {k: v for k, v in self.last_sent.items() if v > window_start}
            
            if len(self.last_sent) >= self.max_messages_per_window:
                return
            
            error_key = f"{record.pathname}:{record.lineno}"
            if error_key in self.error_counts:
                self.error_counts[error_key] += 1
                if self.error_counts[error_key] > 3:
                    return
            else:
                self.error_counts[error_key] = 1
            
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
            self.last_sent[current_time] = current_time
            
        except Exception:
            pass
    
    def emit(self, record):
        # Filter SSL errors at emit level too
        message = record.getMessage()
        for ignored in self.ignored_errors:
            if ignored in message:
                return
                
        if record.levelname in ['ERROR', 'WARNING', 'CRITICAL']:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    if self.queue.qsize() < self.queue.maxsize:
                        asyncio.create_task(self.send_to_webhook(record))
            except Exception:
                pass

webhook_handler = WebhookHandler()

def setup_logging():
    # Filter out pymongo SSL warnings
    logging.getLogger('pymongo').setLevel(logging.ERROR)
    logging.getLogger('pymongo.pool').setLevel(logging.ERROR)
    logging.getLogger('pymongo.topology').setLevel(logging.ERROR)
    
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # Add filter for SSL errors
    class SSLFilter(logging.Filter):
        def filter(self, record):
            return not any(x in str(record.msg) for x in ["SSL", "10054", "10053", "AutoReconnect"])
    
    file_handler.addFilter(SSLFilter())
    webhook_handler.addFilter(SSLFilter())
    
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