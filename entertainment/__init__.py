# cogs/entertainment/__init__.py
# Location: cogs/entertainment/__init__.py
# Description: Entertainment module initialization - auto-loads all entertainment cogs

import os
import importlib
from pathlib import Path

async def setup(bot):
    """Automatically load all .py files in the entertainment folder as cogs"""
    
    # Get the current directory
    current_dir = Path(__file__).parent
    
    # List all Python files in the entertainment folder
    for filename in os.listdir(current_dir):
        # Skip __init__.py and non-python files
        if filename.endswith('.py') and filename != '__init__.py':
            # Remove .py extension to get module name
            module_name = filename[:-3]
            
            try:
                # Import the module dynamically
                module = importlib.import_module(f'.{module_name}', package='cogs.entertainment')
                
                # Check if the module has a setup function
                if hasattr(module, 'setup'):
                    await module.setup(bot)
                    print(f"✅ Loaded entertainment cog: {module_name}")
                else:
                    print(f"⚠️ No setup function in {module_name}")
                    
            except Exception as e:
                print(f"❌ Failed to load entertainment cog {module_name}: {e}")