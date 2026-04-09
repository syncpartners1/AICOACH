import os
import sys

# Add the current directory to sys.path so it can find autogpt
sys.path.append(os.getcwd())

try:
    from autogpt.coaching.config import coaching_config
    print(f"TELEGRAM_BOT_TOKEN: {'[SET]' if coaching_config.telegram_bot_token else '[NOT SET]'}")
    print(f"ADMIN_TELEGRAM_ID: {coaching_config.admin_telegram_id}")
    print(f"SUPABASE_URL: {coaching_config.supabase_url}")
except Exception as e:
    print(f"Error: {e}")
