import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

load_dotenv()

from bot.db import SessionLocal
from bot.models import APIKey

user_id = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

session = SessionLocal()
try:
    keys = session.query(APIKey).filter(APIKey.user_id == user_id).all()
    print(f"Found {len(keys)} keys for user {user_id}:")
    for key in keys:
        print(f"- Exchange: {key.exchange}, Active: {key.is_active}, ID: {key.id}")
finally:
    session.close()
