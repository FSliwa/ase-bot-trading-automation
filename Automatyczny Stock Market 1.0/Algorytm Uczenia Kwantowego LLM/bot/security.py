"""
Security module for encrypting and decrypting sensitive data like API keys.
"""
import os
from cryptography.fernet import Fernet
from typing import Optional
import logging
from dotenv import load_dotenv

# Load environment variables at module import
load_dotenv()

logger = logging.getLogger(__name__)


class SecurityManager:
    """Manages encryption and decryption of sensitive data."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize SecurityManager with encryption key.
        
        Args:
            encryption_key: Base64 encoded encryption key. If None, generates new key.
        """
        if encryption_key:
            self.cipher = Fernet(encryption_key.encode())
        else:
            # Generate new key if not provided
            key = Fernet.generate_key()
            self.cipher = Fernet(key)
            logger.warning(f"Generated new encryption key: {key.decode()}")
            logger.warning("Save this key securely in your .env file as ENCRYPTION_KEY")
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt a string.
        
        Args:
            data: String to encrypt
            
        Returns:
            Base64 encoded encrypted string
        """
        if not data:
            return ""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt an encrypted string. Supports both Fernet-encrypted and plain text.
        
        Args:
            encrypted_data: Base64 encoded encrypted string OR plain text
            
        Returns:
            Decrypted string (or original if not encrypted)
        """
        if not encrypted_data:
            return ""
        
        # Check if data is Fernet encrypted (starts with 'gAAAAA')
        if encrypted_data.startswith('gAAAAA'):
            # Fernet encrypted - decrypt it
            try:
                return self.cipher.decrypt(encrypted_data.encode()).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt Fernet data: {e}")
                raise ValueError("Failed to decrypt data")
        else:
            # Try to decrypt using frontend format (AES-GCM)
            try:
                return self.decrypt_frontend_format(encrypted_data)
            except Exception:
                # If that fails, assume it's plain text (legacy)
                # Plain text - return as is (for backward compatibility with Supabase direct inserts)
                # logger.warning(f"API key stored as plain text (length: {len(encrypted_data)}). Consider re-encrypting.")
                return encrypted_data

    def decrypt_frontend_format(self, encrypted_data: str) -> str:
        """
        Decrypt data encrypted by the frontend (AES-256-GCM).
        
        Args:
            encrypted_data: Base64 encoded string containing IV + Ciphertext
            
        Returns:
            Decrypted string
        """
        try:
            import base64
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend

            # Hardcoded key from frontend: 'trading_api_encryption_key_2024'
            # Padded to 32 bytes as done in frontend logic
            key_string = 'trading_api_encryption_key_2024'
            key_bytes = key_string.ljust(32, '0')[:32].encode('utf-8')
            
            # Decode base64
            combined = base64.b64decode(encrypted_data)
            
            # Extract IV (12 bytes) and ciphertext
            iv = combined[:12]
            ciphertext = combined[12:]
            
            # Decrypt
            cipher = Cipher(
                algorithms.AES(key_bytes),
                modes.GCM(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # GCM mode handles authentication tag automatically if it's part of the ciphertext?
            # In cryptography library, GCM tag is usually passed separately or appended.
            # Wait, Web Crypto API 'AES-GCM' produces ciphertext + tag.
            # The frontend code does: combined.set(iv); combined.set(new Uint8Array(encrypted), iv.length);
            # 'encrypted' from crypto.subtle.encrypt includes the tag at the end.
            # So 'ciphertext' here includes the tag at the end.
            
            # cryptography.hazmat.primitives.ciphers.modes.GCM expects the tag to be passed to finalize() or 
            # if using the high-level API, it might handle it.
            # Actually, for GCM, the tag is the last 16 bytes of the ciphertext usually.
            # Let's check how cryptography library handles GCM.
            # It requires the tag to be passed to the constructor of GCM mode or set later.
            
            # The standard Web Crypto API appends the tag to the end of the ciphertext.
            # So we need to split it. Tag length is usually 128 bits (16 bytes).
            
            tag = ciphertext[-16:]
            actual_ciphertext = ciphertext[:-16]
            
            cipher = Cipher(
                algorithms.AES(key_bytes),
                modes.GCM(iv, tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            decrypted_data = decryptor.update(actual_ciphertext) + decryptor.finalize()
            
            return decrypted_data.decode('utf-8')
            
        except Exception as e:
            # logger.debug(f"Failed to decrypt as frontend format: {e}")
            raise e
    
    def encrypt_dict(self, data: dict, keys_to_encrypt: list) -> dict:
        """
        Encrypt specific keys in a dictionary.
        
        Args:
            data: Dictionary containing data
            keys_to_encrypt: List of keys whose values should be encrypted
            
        Returns:
            Dictionary with encrypted values
        """
        result = data.copy()
        for key in keys_to_encrypt:
            if key in result and result[key]:
                result[f"{key}_encrypted"] = self.encrypt(str(result[key]))
                # Remove original unencrypted key
                del result[key]
        return result
    
    def decrypt_dict(self, data: dict, keys_to_decrypt: list) -> dict:
        """
        Decrypt specific keys in a dictionary.
        
        Args:
            data: Dictionary containing encrypted data
            keys_to_decrypt: List of keys to decrypt (without _encrypted suffix)
            
        Returns:
            Dictionary with decrypted values
        """
        result = data.copy()
        for key in keys_to_decrypt:
            encrypted_key = f"{key}_encrypted"
            if encrypted_key in result and result[encrypted_key]:
                try:
                    result[key] = self.decrypt(result[encrypted_key])
                    # Optionally remove encrypted version
                    # del result[encrypted_key]
                except Exception as e:
                    logger.error(f"Failed to decrypt {key}: {e}")
                    result[key] = None
        return result


# Global instance
_security_manager: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """Get or create global SecurityManager instance."""
    global _security_manager
    
    if _security_manager is None:
        # Try to get encryption key from environment
        encryption_key = os.getenv("ENCRYPTION_KEY")
        if not encryption_key:
            logger.warning("ENCRYPTION_KEY not found in environment variables")
            logger.warning("Generating new key for this session")
        _security_manager = SecurityManager(encryption_key)
    
    return _security_manager

