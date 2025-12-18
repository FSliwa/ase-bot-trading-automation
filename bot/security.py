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
    
    def __init__(self, encryption_key: Optional[str] = None, allow_missing_key: bool = False):
        """
        Initialize SecurityManager with encryption key.
        
        Args:
            encryption_key: Base64 encoded encryption key. If None, works in frontend-only mode.
            allow_missing_key: If True, allow operation without Fernet key (for frontend-encrypted keys).
        
        Note: L1 FIX - If no ENCRYPTION_KEY, Fernet encryption/decryption won't work,
              but frontend-format (AES-GCM) decryption will still work.
        """
        self.cipher = None
        self._has_fernet_key = False
        
        if encryption_key:
            try:
                self.cipher = Fernet(encryption_key.encode())
                self._has_fernet_key = True
            except Exception as e:
                logger.warning(f"Invalid ENCRYPTION_KEY format: {e}")
        
        if not self._has_fernet_key:
            # L1 FIX (modified): Allow operation without Fernet key
            # Frontend-encrypted keys (AES-GCM) will still work
            logger.info(
                "SecurityManager: No ENCRYPTION_KEY configured. "
                "Fernet encryption disabled, but frontend-format (AES-GCM) decryption works."
            )
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt a string.
        
        Args:
            data: String to encrypt
            
        Returns:
            Base64 encoded encrypted string
        
        Raises:
            ValueError: If no Fernet key configured
        """
        if not data:
            return ""
        if not self.cipher:
            raise ValueError("Cannot encrypt: No ENCRYPTION_KEY configured. Set it in .env file.")
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt an encrypted string. Supports both Fernet-encrypted and frontend AES-GCM format.
        
        Args:
            encrypted_data: Base64 encoded encrypted string OR plain text
            
        Returns:
            Decrypted string (or original if not encrypted)
        """
        if not encrypted_data:
            return ""
        
        # 1. Try frontend format (AES-GCM) first - most common for web-encrypted keys
        try:
            return self.decrypt_frontend_format(encrypted_data)
        except Exception:
            pass  # Not frontend format, try other methods
        
        # 2. Check if data is Fernet encrypted (starts with 'gAAAAA')
        if encrypted_data.startswith('gAAAAA') and self.cipher:
            # Fernet encrypted - decrypt it
            try:
                return self.cipher.decrypt(encrypted_data.encode()).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt Fernet data: {e}")
                raise ValueError("Failed to decrypt data")
        
        # 3. If nothing worked, assume it's plain text (legacy)
        # Plain text - return as is (for backward compatibility)
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
    """
    Get or create global SecurityManager instance.
    
    L1 FIX v2: Will warn if ENCRYPTION_KEY not in environment but still work.
    Frontend-encrypted keys (AES-GCM) don't need Fernet key.
    
    Returns:
        SecurityManager instance
    """
    global _security_manager
    
    if _security_manager is None:
        # Try to get encryption key from environment
        encryption_key = os.getenv("ENCRYPTION_KEY")
        if not encryption_key:
            # L1 FIX v2: Warn but don't fail - frontend keys don't need Fernet
            logger.warning(
                "⚠️ ENCRYPTION_KEY not set - Fernet encryption disabled. "
                "Frontend-encrypted keys (AES-GCM) will still work. "
                "For Fernet encryption, set ENCRYPTION_KEY in .env"
            )
            # Create manager with allow_missing_key=True for frontend keys support
            _security_manager = SecurityManager(None, allow_missing_key=True)
        else:
            _security_manager = SecurityManager(encryption_key)
    
    return _security_manager


def generate_encryption_key() -> str:
    """
    L1 FIX: Helper function to generate a new encryption key.
    Use this ONLY for initial setup, not in production code.
    
    Returns:
        Base64-encoded Fernet key string
    """
    key = Fernet.generate_key()
    return key.decode()

