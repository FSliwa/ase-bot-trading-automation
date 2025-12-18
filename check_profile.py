import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

load_dotenv()

from bot.db import SessionLocal
from bot.models import Profile

user_id = "1aa87e38-f100-49d1-85dc-292bc58e25f1"

session = SessionLocal()
try:
    profile = session.query(Profile).filter(Profile.user_id == user_id).first()
    if profile:
        print(f"User Profile: {profile.first_name} {profile.last_name} ({profile.email})")
    else:
        print("Profile not found")
finally:
    session.close()
