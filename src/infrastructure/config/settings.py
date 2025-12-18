"""Application settings with secure secret management."""

import os
from typing import Optional
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with validation and secret management."""
    
    # Database
    database_url: SecretStr
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Redis
    redis_url: SecretStr
    redis_max_connections: int = 100
    
    # Security
    secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours
    
    # VAPID Keys for Push Notifications
    vapid_public_key: str
    vapid_private_key: SecretStr
    
    # SMTP Configuration
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: SecretStr
    smtp_from_email: str
    smtp_from_name: str = "ASE Trading Bot"
    smtp_use_tls: bool = True
    
    # OpenTelemetry
    otel_exporter_endpoint: Optional[str] = None
    otel_service_name: str = "ase-trading-bot"
    otel_environment: str = "production"
    
    # Rate Limiting
    rate_limit_max_requests: int = 100
    rate_limit_window_seconds: int = 60
    
    # AI Configuration
    openai_api_key: Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    ai_max_tokens: int = 4096
    ai_temperature: float = 0.7
    ai_daily_budget_usd: float = 100.0
    
    @field_validator("database_url", "redis_url", "secret_key", "smtp_password", "vapid_private_key", mode='before')
    @classmethod
    def validate_secrets(cls, v):
        """Ensure secrets are not empty and not default values."""
        if not v or v in ["", "changeme", "password", "secret"]:
            raise ValueError("Secret value is empty or using default/weak value")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
        
        # Hide secrets in logs
        json_encoders = {
            SecretStr: lambda v: "***" if v else None,
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


# Create a function to safely log settings
def get_safe_settings_dict() -> dict:
    """Get settings dictionary with secrets redacted."""
    settings = get_settings()
    safe_dict = {}
    
    for key, value in settings.dict().items():
        if isinstance(value, SecretStr):
            safe_dict[key] = "***REDACTED***"
        elif "password" in key.lower() or "secret" in key.lower() or "key" in key.lower():
            safe_dict[key] = "***REDACTED***"
        else:
            safe_dict[key] = value
    
    return safe_dict
