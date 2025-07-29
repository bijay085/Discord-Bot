# setup/enhanced_db_setup.py
# Location: setup/enhanced_db_setup.py
# Description: Enhanced database setup with absolute path handling

import asyncio
import motor.motor_asyncio
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv('setup/.env')

class EnhancedDatabaseSetup:
    def __init__(self):
        self.MONGODB_URI = os.getenv("MONGODB_URI")
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "discord_bot")
        self.OWNER_ID = int(os.getenv("OWNER_ID", "1192694890530869369"))
        self.MAIN_SERVER_ID = int(os.getenv("MAIN_SERVER_ID", "1348916338961154088"))
        self.MAIN_SERVER_INVITE = os.getenv("MAIN_SERVER_INVITE", "https://discord.gg/WVq522fsr3")
        
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.MONGODB_URI)
        self.db = self.client[self.DATABASE_NAME]
        
        # Get absolute base path
        self.base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    async def setup_collections(self):
        print(f"🔧 Setting up database: {self.DATABASE_NAME}")
        print("=" * 50)
        
        collections = await self.db.list_collection_names()
        
        required_collections = [
            "users", "servers", "config", "statistics", 
            "feedback", "analytics", "blacklist_appeals", 
            "cookie_logs", "transactions", "warnings",
            "game_config", "game_stats", "divine_gambles", "bet_history", "rob_history"
        ]
        
        for collection in required_collections:
            if collection not in collections:
                await self.db.create_collection(collection)
                print(f"✅ Created collection: {collection}")
            else:
                print(f"✓ Collection exists: {collection}")
        
        await self.create_enhanced_indexes()
        await self.initialize_bot_config()
        await self.initialize_statistics()
        await self.initialize_analytics()
        await self.setup_cookie_tracking()
        await self.initialize_game_config()
        
    async def create_enhanced_indexes(self):
        print("\n📑 Creating optimized indexes...")
        
        indexes = {
            'users': [
                {'keys': [('user_id', 1)], 'unique': True},
                {'keys': [('points', -1)], 'unique': False},
                {'keys': [('trust_score', -1)], 'unique': False},
                {'keys': [('total_claims', -1)], 'unique': False},
                {'keys': [('blacklisted', 1)], 'unique': False},
                {'keys': [('last_active', -1)], 'unique': False},
                {'keys': [('invite_count', -1)], 'unique': False}
            ],
            'servers': [
                {'keys': [('server_id', 1)], 'unique': True},
                {'keys': [('enabled', 1)], 'unique': False},
                {'keys': [('premium_tier', 1)], 'unique': False}
            ],
            'feedback': [
                {'keys': [('user_id', 1)], 'unique': False},
                {'keys': [('timestamp', -1)], 'unique': False},
                {'keys': [('cookie_type', 1)], 'unique': False},
                {'keys': [('rating', -1)], 'unique': False}
            ],
            'cookie_logs': [
                {'keys': [('user_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('server_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('cookie_type', 1, 'timestamp', -1)], 'unique': False}
            ],
            'transactions': [
                {'keys': [('user_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('type', 1)], 'unique': False}
            ],
            'analytics': [
                {'keys': [('timestamp', -1)], 'unique': False},
                {'keys': [('type', 1)], 'unique': False}
            ],
            'game_stats': [
                {'keys': [('user_id', 1, 'game_type', 1)], 'unique': True},
                {'keys': [('server_id', 1, 'game_type', 1)], 'unique': False}
            ],
            'divine_gambles': [
                {'keys': [('user_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('server_id', 1, 'timestamp', -1)], 'unique': False}
            ],
            'bet_history': [
                {'keys': [('user_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('game_id', 1)], 'unique': False}
            ],
            'rob_history': [
                {'keys': [('robber_id', 1, 'timestamp', -1)], 'unique': False},
                {'keys': [('victim_id', 1, 'timestamp', -1)], 'unique': False}
            ]
        }
        
        for collection, index_list in indexes.items():
            try:
                existing_indexes = await self.db[collection].list_indexes().to_list(None)
                existing_names = {idx['name'] for idx in existing_indexes}
                
                for index_config in index_list:
                    index_name = '_'.join([f"{k}_{v}" for k, v in index_config['keys']])
                    
                    if index_name not in existing_names:
                        await self.db[collection].create_index(
                            index_config['keys'],
                            unique=index_config.get('unique', False)
                        )
                        print(f"✅ Created index {index_name} on {collection}")
                    else:
                        print(f"✓ Index {index_name} exists on {collection}")
                        
            except Exception as e:
                print(f"⚠️ Could not create indexes for {collection}: {e}")
        
    async def initialize_bot_config(self):
        print("\n⚙️ Initializing bot configuration...")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        
        config_doc = {
            "_id": "bot_config",
            "owner_id": self.OWNER_ID,
            "main_server_id": self.MAIN_SERVER_ID,
            "main_server_invite": self.MAIN_SERVER_INVITE,
            "main_log_channel": None,
            "error_webhook": None,
            "analytics_webhook": None,
            "feedback_minutes": 15,
            "maintenance_mode": False,
            "version": "2.0.0",
            "features": {
                "auto_blacklist": True,
                "role_based_system": True,
                "analytics_tracking": True,
                "premium_features": True,
                "invite_tracking": True,
                "auto_directory_creation": True,
                "games_enabled": True
            },
            "point_rates": {
                "daily": 2,
                "invite": 2,
                "boost": 5,
                "vote": 2,
                "feedback_bonus": 1,
                "perfect_rating_bonus": 0
            },
            "cooldown_settings": {
                "daily_hours": 24,
                "feedback_minutes": 15,
                "blacklist_days": 30
            },
            "premium_tiers": {
                "basic": {
                    "name": "Basic",
                    "max_servers": 5,
                    "custom_cookies": False,
                    "advanced_analytics": False
                },
                "pro": {
                    "name": "Pro",
                    "max_servers": 20,
                    "custom_cookies": True,
                    "advanced_analytics": True
                },
                "enterprise": {
                    "name": "Enterprise",
                    "max_servers": -1,
                    "custom_cookies": True,
                    "advanced_analytics": True,
                    "priority_support": True
                }
            },
            "default_cookies": self.get_default_cookies(),
            "default_roles": self.get_default_roles(),
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc)
        }
        
        if not config:
            await self.db.config.insert_one(config_doc)
            print("✅ Created bot configuration")
        else:
            await self.db.config.update_one(
                {"_id": "bot_config"},
                {"$set": {
                    "version": "2.0.0",
                    "features": config_doc["features"],
                    "premium_tiers": config_doc["premium_tiers"],
                    "default_roles": self.get_default_roles(),  # Update roles with new structure
                    "last_updated": datetime.now(timezone.utc)
                }}
            )
            print("✅ Updated bot configuration")
    
    async def initialize_game_config(self):
        print("\n🎮 Initializing game configurations...")
        
        game_config = await self.db.game_config.find_one({"_id": "global_games"})
        
        if not game_config:
            games_doc = {
                "_id": "global_games",
                "games": {
                    "slots": {
                        "enabled": True,
                        "name": "Slot Machine",
                        "description": "Classic 3-reel slot machine",
                        "emoji": "🎰",
                        "min_bet": 5,
                        "max_bet": 200,
                        "max_bet_percentage": 0.25,
                        "cooldown": 10,
                        "symbols": {
                            "🍒": {"name": "Cherry", "payout": 1.5, "weight": 20},
                            "🍋": {"name": "Lemon", "payout": 2, "weight": 10},
                            "🍊": {"name": "Orange", "payout": 3, "weight": 5},
                            "🍇": {"name": "Grapes", "payout": 5, "weight": 3},
                            "💎": {"name": "Diamond", "payout": 10, "weight": 1},
                            "7️⃣": {"name": "Seven", "payout": 50, "weight": 0.2}
                        }
                    },
                    "bet": {
                        "enabled": True,
                        "name": "Number Betting",
                        "description": "Guess the winning number",
                        "emoji": "🎲",
                        "solo_enabled": True,
                        "group_enabled": True,
                        "max_players": 50,
                        "join_timer": 60,
                        "guess_timer": 30,
                        "solo_range": 10,
                        "group_base_range": 10,
                        "group_range_per_player": 2,
                        "rewards": {
                            "solo_exact": 1.5,
                            "solo_close": 0.15,
                            "group_winner": 1.0,
                            "group_closest": 0.5
                        }
                    },
                    "rob": {
                        "enabled": True,
                        "name": "Robbery System",
                        "description": "Steal points from other users",
                        "emoji": "🎭",
                        "daily_attempts": 2,
                        "cooldown_hours": 3,
                        "daily_robbed_limit": 2,
                        "steal_percentage": {"min": 20, "max": 30},
                        "penalty_percentage": 30,
                        "trust_rewards": {"success": 0.5, "failure": -1},
                        "success_rates": {
                            "victim_under_20": 90,
                            "victim_20_40": 70,
                            "victim_40_60": 50,
                            "victim_60_plus": 30,
                            "lower_trust": 20
                        }
                    },
                    "gamble": {
                        "enabled": True,
                        "name": "Divine Gamble",
                        "description": "Ultimate risk for divine blessing",
                        "emoji": "🎰",
                        "win_chance": 5,
                        "cooldown_days": 7,
                        "requirements": {
                            "invites": 5,
                            "trust_score": 60,
                            "points": 20
                        },
                        "entry_cost": {
                            "trust": 15,
                            "points": 10
                        },
                        "rewards": {
                            "trust_return": 45,
                            "points_return": 130,
                            "curse_duration_hours": 24,
                            "blessing_duration_days": 7
                        }
                    },
                    "giveaway": {
                        "enabled": True,
                        "name": "Points Giveaway",
                        "description": "Free points giveaways",
                        "emoji": "🎁",
                        "owner_only": True,
                        "entry_emoji": "🎉",
                        "max_duration_days": 7,
                        "min_duration_minutes": 5,
                        "max_active": 5
                    }
                },
                "global_settings": {
                    "games_channel_required": True,
                    "announce_big_wins": True,
                    "big_win_threshold": 500,
                    "daily_game_limit": 100,
                    "trust_affects_games": True
                },
                "created_at": datetime.now(timezone.utc),
                "last_updated": datetime.now(timezone.utc)
            }
            
            await self.db.game_config.insert_one(games_doc)
            print("✅ Created game configurations")
        else:
            print("✓ Game configurations exist")
            
    def get_default_cookies(self):
        # Use absolute paths
        base_cookie_dir = os.path.join(self.base_path, "cookies")
        
        return {
            "netflix": {
                "cost": 5, 
                "cooldown": 72, 
                "directory": os.path.join(base_cookie_dir, "netflix"), 
                "enabled": True,
                "description": "Premium Netflix accounts",
                "emoji": "🎬",
                "category": "streaming"
            },
            "spotify": {
                "cost": 3, 
                "cooldown": 48, 
                "directory": os.path.join(base_cookie_dir, "spotify"), 
                "enabled": True,
                "description": "Premium Spotify accounts",
                "emoji": "🎵",
                "category": "music"
            },
            "prime": {
                "cost": 4, 
                "cooldown": 48, 
                "directory": os.path.join(base_cookie_dir, "prime"), 
                "enabled": True,
                "description": "Amazon Prime accounts",
                "emoji": "📦",
                "category": "streaming"
            },
            "jiohotstar": {
                "cost": 3, 
                "cooldown": 48, 
                "directory": os.path.join(base_cookie_dir, "jiohotstar"), 
                "enabled": True,
                "description": "JioHotstar Premium accounts",
                "emoji": "⭐",
                "category": "streaming"
            },
            "tradingview": {
                "cost": 8, 
                "cooldown": 48, 
                "directory": os.path.join(base_cookie_dir, "tradingview"), 
                "enabled": True,
                "description": "TradingView Pro accounts",
                "emoji": "📈",
                "category": "tools"
            },
            "chatgpt": {
                "cost": 10, 
                "cooldown": 72, 
                "directory": os.path.join(base_cookie_dir, "chatgpt"), 
                "enabled": True,
                "description": "ChatGPT Plus accounts",
                "emoji": "🤖",
                "category": "ai"
            },
            "claude": {
                "cost": 12, 
                "cooldown": 72, 
                "directory": os.path.join(base_cookie_dir, "claude"), 
                "enabled": True,
                "description": "Claude Pro accounts",
                "emoji": "🧠",
                "category": "ai"
            },
            "peacock": {
                "cost": 4, 
                "cooldown": 24, 
                "directory": os.path.join(base_cookie_dir, "peacock"), 
                "enabled": True,
                "description": "Peacock Premium accounts",
                "emoji": "🦚",
                "category": "streaming"
            },
            "crunchyroll": {
                "cost": 4, 
                "cooldown": 24, 
                "directory": os.path.join(base_cookie_dir, "crunchyroll"), 
                "enabled": True,
                "description": "Crunchyroll Premium accounts",
                "emoji": "🍙",
                "category": "anime"
            },
            "canalplus": {
                "cost": 6, 
                "cooldown": 48, 
                "directory": os.path.join(base_cookie_dir, "canalplus"), 
                "enabled": True,
                "description": "Canal+ Premium accounts",
                "emoji": "📺",
                "category": "streaming"
            }
        }
    
    def get_default_roles(self):
        # Get cookie types for easy reference
        cookie_types = list(self.get_default_cookies().keys())
        
        return {
            "free": {
                "name": "Free",
                "description": "Basic access with limited cookies",
                "emoji": "🆓",
                "daily_bonus": 0,
                "trust_multiplier": 1.0,
                "game_benefits": {
                    "slots_max_bet_bonus": 0,
                    "rob_success_bonus": 0,
                    "bet_profit_multiplier": 1.0
                },
                "cookie_access": {
                    "netflix": {
                        "enabled": True,
                        "cost": 5,  # default cost
                        "cooldown": 72,  # default cooldown
                        "daily_limit": 1
                    },
                    "spotify": {
                        "enabled": True,
                        "cost": 3,
                        "cooldown": 48,
                        "daily_limit": 1
                    },
                    "prime": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 48,
                        "daily_limit": 1
                    },
                    # Other cookies disabled for free role
                    "jiohotstar": {"enabled": False},
                    "tradingview": {"enabled": False},
                    "chatgpt": {"enabled": False},
                    "claude": {"enabled": False},
                    "peacock": {"enabled": False},
                    "crunchyroll": {"enabled": False},
                    "canalplus": {"enabled": False}
                }
            },
            "premium": {
                "name": "Premium",
                "description": "Enhanced access with reduced costs",
                "emoji": "⭐",
                "daily_bonus": 5,
                "trust_multiplier": 1.5,
                "game_benefits": {
                    "slots_max_bet_bonus": 50,
                    "rob_success_bonus": 5,
                    "bet_profit_multiplier": 1.1
                },
                "cookie_access": {
                    "netflix": {
                        "enabled": True,
                        "cost": 3,  # reduced cost
                        "cooldown": 48,  # reduced cooldown
                        "daily_limit": 2
                    },
                    "spotify": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "prime": {
                        "enabled": True,
                        "cost": 3,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "jiohotstar": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "tradingview": {
                        "enabled": True,
                        "cost": 6,
                        "cooldown": 48,
                        "daily_limit": 1
                    },
                    "chatgpt": {
                        "enabled": True,
                        "cost": 8,
                        "cooldown": 48,
                        "daily_limit": 1
                    },
                    "claude": {
                        "enabled": False
                    },
                    "peacock": {
                        "enabled": True,
                        "cost": 3,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "crunchyroll": {
                        "enabled": True,
                        "cost": 3,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "canalplus": {
                        "enabled": True,
                        "cost": 5,
                        "cooldown": 48,
                        "daily_limit": 1
                    }
                }
            },
            "vip": {
                "name": "VIP",
                "description": "VIP access with major discounts",
                "emoji": "💎",
                "daily_bonus": 10,
                "trust_multiplier": 2.0,
                "game_benefits": {
                    "slots_max_bet_bonus": 100,
                    "rob_success_bonus": 10,
                    "bet_profit_multiplier": 1.2
                },
                "cookie_access": {
                    "netflix": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 24,
                        "daily_limit": 3
                    },
                    "spotify": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "prime": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "jiohotstar": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "tradingview": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "chatgpt": {
                        "enabled": True,
                        "cost": 5,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "claude": {
                        "enabled": True,
                        "cost": 8,
                        "cooldown": 48,
                        "daily_limit": 1
                    },
                    "peacock": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "crunchyroll": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "canalplus": {
                        "enabled": True,
                        "cost": 3,
                        "cooldown": 24,
                        "daily_limit": 2
                    }
                }
            },
            "elite": {
                "name": "Elite",
                "description": "Elite access with minimal costs",
                "emoji": "🎯",
                "daily_bonus": 20,
                "trust_multiplier": 2.5,
                "game_benefits": {
                    "slots_max_bet_bonus": 200,
                    "rob_success_bonus": 15,
                    "bet_profit_multiplier": 1.3
                },
                "cookie_access": {
                    "netflix": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 12,
                        "daily_limit": 5
                    },
                    "spotify": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "prime": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "jiohotstar": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "tradingview": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "chatgpt": {
                        "enabled": True,
                        "cost": 3,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "claude": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 24,
                        "daily_limit": 2
                    },
                    "peacock": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "crunchyroll": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "canalplus": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    }
                }
            },
            "booster": {
                "name": "Booster",
                "description": "Server boosters get amazing perks",
                "emoji": "🚀",
                "daily_bonus": 20,
                "trust_multiplier": 3.0,
                "game_benefits": {
                    "slots_max_bet_bonus": 300,
                    "rob_success_bonus": 20,
                    "bet_profit_multiplier": 1.5
                },
                "cookie_access": {
                    # All cookies very cheap/free for boosters
                    "netflix": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 3,
                        "daily_limit": 10
                    },
                    "spotify": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 3,
                        "daily_limit": 10
                    },
                    "prime": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 3,
                        "daily_limit": 10
                    },
                    "jiohotstar": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 3,
                        "daily_limit": 10
                    },
                    "tradingview": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "chatgpt": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 6,
                        "daily_limit": 5
                    },
                    "claude": {
                        "enabled": True,
                        "cost": 2,
                        "cooldown": 12,
                        "daily_limit": 3
                    },
                    "peacock": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 3,
                        "daily_limit": 10
                    },
                    "crunchyroll": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 3,
                        "daily_limit": 10
                    },
                    "canalplus": {
                        "enabled": True,
                        "cost": 1,
                        "cooldown": 6,
                        "daily_limit": 5
                    }
                }
            },
            "staff": {
                "name": "Staff",
                "description": "Staff members have special privileges",
                "emoji": "🛡️",
                "daily_bonus": 5,
                "trust_multiplier": 5.0,
                "game_benefits": {
                    "slots_max_bet_bonus": 500,
                    "rob_success_bonus": 25,
                    "bet_profit_multiplier": 2.0
                },
                "cookie_access": {
                    # Staff can test all cookies with moderate costs
                    "netflix": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1  # unlimited
                    },
                    "spotify": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "prime": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "jiohotstar": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "tradingview": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "chatgpt": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "claude": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "peacock": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "crunchyroll": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    },
                    "canalplus": {
                        "enabled": True,
                        "cost": 4,
                        "cooldown": 5,
                        "daily_limit": -1
                    }
                }
            }
        }
    
    async def initialize_statistics(self):
        print("\n📊 Initializing statistics tracking...")
        
        stats = await self.db.statistics.find_one({"_id": "global_stats"})
        
        if not stats:
            cookie_types = list(self.get_default_cookies().keys())
            
            stats_doc = {
                "_id": "global_stats",
                "total_claims": {cookie: 0 for cookie in cookie_types},
                "weekly_claims": {cookie: 0 for cookie in cookie_types},
                "monthly_claims": {cookie: 0 for cookie in cookie_types},
                "all_time_claims": 0,
                "total_users": 0,
                "total_servers": 0,
                "total_points_distributed": 0,
                "total_blacklists": 0,
                "game_stats": {
                    "slots_played": 0,
                    "slots_won": 0,
                    "slots_jackpots": 0,
                    "bets_created": 0,
                    "bets_completed": 0,
                    "rob_attempts": 0,
                    "rob_successes": 0,
                    "divine_gambles": 0,
                    "divine_wins": 0,
                    "giveaways_created": 0,
                    "giveaway_points": 0
                },
                "created_at": datetime.now(timezone.utc),
                "last_reset": datetime.now(timezone.utc)
            }
            
            await self.db.statistics.insert_one(stats_doc)
            print("✅ Created global statistics")
        else:
            # Update existing stats to include game stats
            if "game_stats" not in stats:
                await self.db.statistics.update_one(
                    {"_id": "global_stats"},
                    {"$set": {
                        "game_stats": {
                            "slots_played": 0,
                            "slots_won": 0,
                            "slots_jackpots": 0,
                            "bets_created": 0,
                            "bets_completed": 0,
                            "rob_attempts": 0,
                            "rob_successes": 0,
                            "divine_gambles": 0,
                            "divine_wins": 0,
                            "giveaways_created": 0,
                            "giveaway_points": 0
                        }
                    }}
                )
                print("✅ Updated statistics with game stats")
            else:
                print("✓ Statistics tracking exists")
    
    async def initialize_analytics(self):
        print("\n📈 Initializing analytics collection...")
        
        analytics_docs = [
            {
                "_id": "bot_analytics",
                "total_users": 0,
                "total_servers": 0,
                "total_commands": 0,
                "total_cookies": 0,
                "total_transactions": 0,
                "average_trust_score": 50,
                "total_games_played": 0,
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "command_usage",
                "commands": {
                    cmd: {
                        "total": 0,
                        "today": 0,
                        "this_week": 0,
                        "this_month": 0,
                        "unique_users": [],
                        "guilds": [],
                        "average_execution_time": 0
                    } for cmd in ["cookie", "daily", "points", "help", "stock", 
                                  "feedback", "invites", "status", "leaderboard", 
                                  "refresh", "analytics", "slots", "bet", "rob", 
                                  "gamble", "pgiveaway", "games"]
                },
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "cookie_performance",
                "cookies": {
                    cookie: {
                        "total_claims": 0,
                        "successful_claims": 0,
                        "failed_claims": 0,
                        "average_rating": 0,
                        "feedback_count": 0,
                        "blacklist_rate": 0,
                        "stock_alerts": 0
                    } for cookie in self.get_default_cookies().keys()
                },
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "user_behavior",
                "average_session_length": 0,
                "retention_rate": {
                    "daily": 0,
                    "weekly": 0,
                    "monthly": 0
                },
                "churn_rate": 0,
                "engagement_metrics": {
                    "commands_per_user": 0,
                    "claims_per_user": 0,
                    "feedback_rate": 0,
                    "games_per_user": 0
                },
                "last_updated": datetime.now(timezone.utc)
            },
            {
                "_id": "game_analytics",
                "games": {
                    "slots": {
                        "total_plays": 0,
                        "total_wins": 0,
                        "total_wagered": 0,
                        "total_payout": 0,
                        "house_edge": 0,
                        "biggest_win": 0,
                        "average_bet": 0
                    },
                    "bet": {
                        "total_games": 0,
                        "solo_games": 0,
                        "group_games": 0,
                        "total_pot": 0,
                        "average_players": 0,
                        "biggest_pot": 0
                    },
                    "rob": {
                        "total_attempts": 0,
                        "successful_robs": 0,
                        "failed_robs": 0,
                        "points_stolen": 0,
                        "penalties_paid": 0,
                        "most_robbed_user": None
                    },
                    "gamble": {
                        "total_gambles": 0,
                        "blessed_count": 0,
                        "cursed_count": 0,
                        "trust_lost": 0,
                        "trust_gained": 0,
                        "points_lost": 0,
                        "points_gained": 0
                    },
                    "giveaway": {
                        "total_giveaways": 0,
                        "total_points_given": 0,
                        "average_participants": 0,
                        "biggest_giveaway": 0
                    }
                },
                "last_updated": datetime.now(timezone.utc)
            }
        ]
        
        for doc in analytics_docs:
            existing = await self.db.analytics.find_one({"_id": doc["_id"]})
            if not existing:
                await self.db.analytics.insert_one(doc)
                print(f"✅ Created {doc['_id']} analytics")
            else:
                # Update existing docs with game analytics
                if doc["_id"] == "game_analytics" and not existing.get("games"):
                    await self.db.analytics.update_one(
                        {"_id": "game_analytics"},
                        {"$set": doc}
                    )
                    print(f"✅ Updated game analytics")
                else:
                    print(f"✓ {doc['_id']} analytics exists")
    
    async def setup_cookie_tracking(self):
        print("\n🍪 Setting up cookie tracking system...")
        
        tracking_doc = await self.db.config.find_one({"_id": "cookie_tracking"})
        
        if not tracking_doc:
            tracking = {
                "_id": "cookie_tracking",
                "file_tracking": {},
                "distribution_history": [],
                "stock_thresholds": {
                    "critical": 5,
                    "low": 10,
                    "medium": 20,
                    "good": 50
                },
                "auto_restock": {
                    "enabled": False,
                    "sources": [],
                    "check_interval": 3600
                },
                "quality_control": {
                    "enabled": True,
                    "min_rating": 3.0,
                    "blacklist_threshold": 5
                },
                "created_at": datetime.now(timezone.utc)
            }
            
            await self.db.config.insert_one(tracking)
            print("✅ Created cookie tracking system")
        else:
            print("✓ Cookie tracking exists")
    
    async def create_directories(self):
        print("\n📁 Creating cookie directories...")
        
        base_dir = Path(self.base_path) / "cookies"
        base_dir.mkdir(exist_ok=True)
        
        cookies = self.get_default_cookies()
        for cookie_type, config in cookies.items():
            cookie_dir = Path(config["directory"])
            cookie_dir.mkdir(parents=True, exist_ok=True)
            
            readme_path = cookie_dir / "README.txt"
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
"""
                readme_path.write_text(readme_content)
            
            print(f"✅ Created directory: {cookie_dir}")
    
    async def setup_sample_data(self):
        print("\n📝 Creating sample data...")
        
        sample_server = {
            "server_id": 999999999,
            "server_name": "Test Server",
            "enabled": True,
            "setup_complete": True,
            "channels": {
                "cookie": None,
                "feedback": None,
                "log": None,
                "announcement": None,
                "games": None
            },
            "cookies": self.get_default_cookies(),
            "role_based": True,
            "roles": {
                # This will be populated when roles are created with specific cookie settings
            },
            "games": {
                "enabled": True,
                "channel_required": True,
                "games_config": {
                    "slots": {"enabled": True, "custom_settings": {}},
                    "bet": {"enabled": True, "custom_settings": {}},
                    "rob": {"enabled": True, "custom_settings": {}},
                    "gamble": {"enabled": True, "custom_settings": {}},
                    "giveaway": {"enabled": True, "custom_settings": {}}
                }
            },
            "settings": {
                "feedback_required": True,
                "feedback_timeout": 15,
                "max_daily_claims": 10,
                "blacklist_after_warnings": 3
            },
            "created_at": datetime.now(timezone.utc)
        }
        
        existing = await self.db.servers.find_one({"server_id": sample_server["server_id"]})
        if not existing:
            await self.db.servers.insert_one(sample_server)
            print("✅ Created sample server")
        
        sample_users = [
            {
                "user_id": 111111111,
                "username": "test_user1",
                "points": 50,
                "total_earned": 50,
                "total_spent": 0,
                "trust_score": 75,
                "cookie_claims": {"netflix": 5, "spotify": 3},
                "total_claims": 8,
                "weekly_claims": 8,
                "daily_claimed": None,
                "invite_count": 5,
                "blacklisted": False,
                "daily_claims": {},  # Track daily claims per cookie type
                "game_stats": {
                    "slots": {"played": 0, "won": 0, "profit": 0},
                    "bet": {"played": 0, "won": 0, "profit": 0},
                    "rob": {"attempts": 0, "successes": 0, "profit": 0},
                    "gamble": {"attempts": 0, "wins": 0}
                }
            },
            {
                "user_id": 222222222,
                "username": "premium_user",
                "points": 100,
                "total_earned": 150,
                "total_spent": 50,
                "trust_score": 90,
                "cookie_claims": {"chatgpt": 2, "claude": 1},
                "total_claims": 3,
                "weekly_claims": 3,
                "daily_claimed": None,
                "invite_count": 10,
                "blacklisted": False,
                "daily_claims": {},  # Track daily claims per cookie type
                "game_stats": {
                    "slots": {"played": 0, "won": 0, "profit": 0},
                    "bet": {"played": 0, "won": 0, "profit": 0},
                    "rob": {"attempts": 0, "successes": 0, "profit": 0},
                    "gamble": {"attempts": 0, "wins": 0}
                }
            }
        ]
        
        for user_data in sample_users:
            user_data.update({
                "account_created": datetime.now(timezone.utc),
                "first_seen": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
                "blacklist_expires": None,
                "preferences": {
                    "dm_notifications": True,
                    "claim_confirmations": True,
                    "feedback_reminders": True
                },
                "statistics": {
                    "feedback_streak": 0,
                    "perfect_ratings": 0,
                    "favorite_cookie": None,
                    "divine_gambles": 0,
                    "divine_wins": 0,
                    "divine_losses": 0,
                    "rob_wins": 0,
                    "rob_losses": 0,
                    "rob_winnings": 0,
                    "rob_losses_amount": 0,
                    "times_robbed": 0,
                    "amount_stolen_from": 0,
                    "slots_played": 0,
                    "slots_won": 0,
                    "slots_lost": 0,
                    "slots_profit": 0,
                    "slots_biggest_win": 0,
                    "slots_current_streak": 0,
                    "slots_best_streak": 0
                }
            })
            
            existing = await self.db.users.find_one({"user_id": user_data["user_id"]})
            if not existing:
                await self.db.users.insert_one(user_data)
                print(f"✅ Created sample user: {user_data['username']}")
    
    async def verify_setup(self):
        print("\n✅ Verifying setup...")
        
        collections = await self.db.list_collection_names()
        config = await self.db.config.find_one({"_id": "bot_config"})
        game_config = await self.db.game_config.find_one({"_id": "global_games"})
        
        checks = {
            "Collections": len(collections),
            "Configuration": "✅" if config else "❌",
            "Game Configuration": "✅" if game_config else "❌",
            "Cookie Types": len(config.get("default_cookies", {})) if config else 0,
            "Role Types": len(config.get("default_roles", {})) if config else 0,
            "Game Types": len(game_config.get("games", {})) if game_config else 0,
            "Users": await self.db.users.count_documents({}),
            "Servers": await self.db.servers.count_documents({})
        }
        
        print("\n📋 Setup Verification:")
        for item, value in checks.items():
            print(f"  {item}: {value}")
    
    async def show_summary(self):
        print("\n" + "=" * 50)
        print("📊 DATABASE SETUP SUMMARY")
        print("=" * 50)
        
        stats = {
            "Total Collections": len(await self.db.list_collection_names()),
            "Total Users": await self.db.users.count_documents({}),
            "Total Servers": await self.db.servers.count_documents({}),
            "Blacklisted Users": await self.db.users.count_documents({"blacklisted": True}),
            "Total Feedback": await self.db.feedback.count_documents({}),
            "Game Configurations": await self.db.game_config.count_documents({})
        }
        
        for key, value in stats.items():
            print(f"{key}: {value}")
        
        config = await self.db.config.find_one({"_id": "bot_config"})
        if config:
            print(f"\nBot Version: {config.get('version', 'Unknown')}")
            print(f"Owner ID: {config.get('owner_id')}")
            print(f"Maintenance Mode: {config.get('maintenance_mode', False)}")
            print(f"Games Enabled: {config.get('features', {}).get('games_enabled', False)}")
    
    async def run(self):
        try:
            print("🚀 Enhanced Database Setup Starting...")
            print("=" * 50)
            
            await self.client.admin.command('ping')
            print("✅ Successfully connected to MongoDB!\n")
            
            await self.setup_collections()
            await self.create_directories()
            await self.setup_sample_data()
            await self.verify_setup()
            await self.show_summary()
            
            print("\n✅ Enhanced database setup completed successfully!")
            print("=" * 50)
            
        except Exception as e:
            print(f"\n❌ Error during setup: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.client.close()
            print("\n🔌 Database connection closed.")

async def main():
    setup = EnhancedDatabaseSetup()
    await setup.run()

if __name__ == "__main__":
    asyncio.run(main())