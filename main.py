import asyncio
import sys
from bot_core.bot import CookieBot
import os

async def main():
    print("""
    ╔═══════════════════════════════════════╗
    ║      🍪 COOKIE BOT PREMIUM v2.0 🍪     ║
    ╠═══════════════════════════════════════╣
    ║  Advanced Cookie Distribution System   ║
    ║      Created with ❤️ by YourName       ║
    ╚═══════════════════════════════════════╝
    """)
    
    bot = CookieBot()
    
    try:
        print("🚀 Starting Cookie Bot...")
        await bot.start(os.getenv("BOT_TOKEN"))
    except KeyboardInterrupt:
        print("⌨️ Received interrupt signal")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")