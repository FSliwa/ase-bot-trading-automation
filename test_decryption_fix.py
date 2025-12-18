import sys
import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Add the current directory to sys.path so we can import from bot
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.security import SecurityManager

def simulate_frontend_encryption(text, key_string):
    # Simulate the frontend encryption logic
    # 1. Pad key to 32 bytes
    key_bytes = key_string.ljust(32, '0')[:32].encode('utf-8')
    
    # 2. Generate random IV (12 bytes)
    iv = os.urandom(12)
    
    # 3. Encrypt using AES-GCM
    cipher = Cipher(
        algorithms.AES(key_bytes),
        modes.GCM(iv),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(text.encode('utf-8')) + encryptor.finalize()
    
    # 4. Get tag
    tag = encryptor.tag
    
    # 5. Combine IV + Ciphertext + Tag
    # Frontend does: combined.set(iv); combined.set(new Uint8Array(encrypted), iv.length);
    # Web Crypto API 'encrypted' includes tag at the end.
    combined = iv + ciphertext + tag
    
    # 6. Base64 encode
    return base64.b64encode(combined).decode('utf-8')

def test_decryption():
    print("Testing decryption fix...")
    
    original_text = "my_secret_api_key_123"
    frontend_key = "trading_api_encryption_key_2024"
    
    # 1. Encrypt using simulated frontend logic
    encrypted_data = simulate_frontend_encryption(original_text, frontend_key)
    print(f"Encrypted data (frontend format): {encrypted_data}")
    
    # 2. Decrypt using SecurityManager
    sm = SecurityManager()
    decrypted_text = sm.decrypt(encrypted_data)
    
    print(f"Decrypted text: {decrypted_text}")
    
    if decrypted_text == original_text:
        print("SUCCESS: Decryption matches original text!")
    else:
        print(f"FAILURE: Decryption mismatch. Expected '{original_text}', got '{decrypted_text}'")
        sys.exit(1)

if __name__ == "__main__":
    test_decryption()
