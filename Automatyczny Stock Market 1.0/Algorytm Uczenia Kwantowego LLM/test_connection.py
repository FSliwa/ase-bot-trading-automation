import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Load .env from the correct location (Algorytm Uczenia Kwantowego LLM/.env)
env_path = Path(__file__).parent / ".env"
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

from bot.db import SessionLocal
from bot.models import APIKey
from bot.security import get_security_manager
from bot.http.ccxt_adapter import CCXTAdapter

async def main():
    user_id = "1aa87e38-f100-49d1-85dc-292bc58e25f1"
    print(f"Testing connection for user: {user_id}")

    session = SessionLocal()
    try:
        # 1. Get the key
        key_record = session.query(APIKey).filter(APIKey.user_id == user_id, APIKey.is_active == True).first()
        
        if not key_record:
            print("No active API key found for user.")
            return

        print(f"Found key for exchange: {key_record.exchange}")
        
        # 2. Decrypt credentials
        security = get_security_manager()
        
        # Debug raw values
        print(f"Raw encrypted key length: {len(key_record.encrypted_api_key)}")
        print(f"Raw encrypted key prefix: {key_record.encrypted_api_key[:10]}...")
        
        api_key = security.decrypt(key_record.encrypted_api_key)
        api_secret = security.decrypt(key_record.encrypted_api_secret)
        
        print(f"Decrypted key length: {len(api_key)}")
        print(f"Decrypted key prefix: {api_key[:5]}...")
        
        # Check if key looks like hex
        import string
        is_hex = all(c in string.hexdigits for c in api_key)
        print(f"Is key hex? {is_hex}")
        
        # 3. Test connection
        print(f"Connecting to {key_record.exchange}...")
        
        # Try standard connection first
        await try_connect(key_record.exchange, api_key, api_secret, key_record.is_testnet, "Standard")
        
        # If hex, try decoding
        if is_hex and len(api_key) > 60: # Arbitrary threshold
             try:
                 decoded_key = bytes.fromhex(api_key).decode('utf-8')
                 print(f"Decoded hex key: {decoded_key[:5]}...")
                 await try_connect(key_record.exchange, decoded_key, api_secret, key_record.is_testnet, "Hex Decoded")
             except Exception as e:
                 print(f"Hex decode failed: {e}")

        # Try Base64 decoding (recursive)
        import base64
        current_val = api_key
        for i in range(1, 4):
            try:
                # Check if it looks like Base64 (length multiple of 4, alphanumeric + +/=)
                if len(current_val) % 4 == 0:
                    decoded_bytes = base64.b64decode(current_val)
                    try:
                        decoded_str = decoded_bytes.decode('utf-8')
                        print(f"Base64 decode level {i}: {decoded_str[:10]}...")
                        await try_connect(key_record.exchange, decoded_str, api_secret, key_record.is_testnet, f"Base64 Level {i}")
                        current_val = decoded_str
                    except UnicodeDecodeError:
                        print(f"Base64 decode level {i} resulted in binary.")
                        break
                else:
                    print(f"Level {i} not valid Base64 length.")
                    break
            except Exception as e:
                print(f"Base64 decode level {i} failed: {e}")
                break
                
        # Try AES-GCM decryption (Hypothesis: 12 byte nonce + data + 16 byte tag)
        print("Attempting AES-GCM decryption...")
        try:
            import base64
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            
            # Get the raw key from env
            env_key_b64 = os.getenv("ENCRYPTION_KEY")
            if not env_key_b64:
                print("ENCRYPTION_KEY not found for AES-GCM")
            else:
                # Fernet keys are 32 bytes base64url encoded
                key_bytes = base64.urlsafe_b64decode(env_key_b64)
                
                # Decode the API key from base64
                data_bytes = base64.b64decode(api_key)
                
                # AES-GCM usually: Nonce (12) + Ciphertext + Tag (16)
                # But python cryptography AESGCM.decrypt expects nonce and (ciphertext + tag)
                nonce = data_bytes[:12]
                ciphertext_with_tag = data_bytes[12:]
                
                aesgcm = AESGCM(key_bytes)
                decrypted_gcm = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
                
                decrypted_gcm_str = decrypted_gcm.decode('utf-8')
                print(f"AES-GCM decryption SUCCESS: {decrypted_gcm_str[:5]}...")
                await try_connect(key_record.exchange, decrypted_gcm_str, api_secret, key_record.is_testnet, "AES-GCM")
                
        except Exception as e:
            print(f"AES-GCM decryption failed: {e}")
            
        # Try forcing Fernet decryption on the original key string
        print("Attempting forced Fernet decryption...")
        try:
            forced_decrypted = security.cipher.decrypt(key_record.encrypted_api_key.encode()).decode()
            print(f"Forced Fernet decryption SUCCESS: {forced_decrypted[:5]}...")
            await try_connect(key_record.exchange, forced_decrypted, api_secret, key_record.is_testnet, "Forced Fernet")
        except Exception as e:
            print(f"Forced Fernet decryption failed: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        session.close()

async def try_connect(exchange_name, api_key, api_secret, testnet, label):
    print(f"\n--- Attempting connection ({label}) ---")
    adapter = CCXTAdapter(
        exchange_name=exchange_name.lower(),
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        futures=False
    )
    
    try:
        info = await adapter.get_account_info()
        print(f"[{label}] Connection SUCCESSFUL!")
        print(f"[{label}] Account Balance (USDT): Total={info.total}, Free={info.free}, Used={info.used}")
    except Exception as e:
        print(f"[{label}] Connection FAILED: {e}")
    finally:
        await adapter.close()

if __name__ == "__main__":
    asyncio.run(main())
