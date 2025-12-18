import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from bot.db import SessionLocal
from bot.models import APIKey
from bot.security import get_security_manager

def analyze_keys():
    session = SessionLocal()
    security = get_security_manager()
    
    try:
        print(f"Using ENCRYPTION_KEY: {os.getenv('ENCRYPTION_KEY', 'NOT SET')[:5]}...")
        
        keys = session.query(APIKey).all()
        print(f"Found {len(keys)} total keys in DB.")
        
        for i, key in enumerate(keys):
            print(f"\n--- Key {i+1} ---")
            print(f"User ID: {key.user_id}")
            print(f"Exchange: {key.exchange}")
            print(f"Length: {len(key.encrypted_api_key)}")
            print(f"Prefix: {key.encrypted_api_key[:10]}...")
            
            is_fernet = key.encrypted_api_key.startswith("gAAAAA")
            print(f"Is Fernet format? {is_fernet}")
            
            if is_fernet:
                try:
                    decrypted = security.decrypt(key.encrypted_api_key)
                    print(f"✅ Decryption SUCCESS! Key starts with: {decrypted[:4]}...")
                except Exception as e:
                    print(f"❌ Decryption FAILED: {e}")
            else:
                print("⚠️ Not Fernet format. Skipping decryption attempt.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    analyze_keys()
