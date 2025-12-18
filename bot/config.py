from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class GeminiConfig:
    """Gemini AI configuration"""
    api_key: Optional[str]
    model: str
    temperature: float
    max_tokens: int


@dataclass
class AppConfig:
    api_key: Optional[str]
    api_secret: Optional[str]
    use_testnet: bool
    max_leverage: float
    require_stop_loss_live: bool


@dataclass
class OAuthConfig:
    """OAuth configuration for exchanges"""
    # Binance OAuth
    binance_client_id: Optional[str]
    binance_client_secret: Optional[str]
    binance_redirect_uri: str
    
    # Bybit OAuth (Broker API)
    bybit_client_id: Optional[str]
    bybit_client_secret: Optional[str]
    bybit_redirect_uri: str
    
    # General settings
    base_url: str
    encryption_key: Optional[str]


def _to_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_float(value: Optional[str], default: float) -> float:
    try:
        return float(value) if value is not None and value != "" else default
    except Exception:
        return default


def load_config() -> AppConfig:
    """Load configuration from environment variables and optional .env file."""
    load_dotenv()  # Loads from nearest .env if present

    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    use_testnet = _to_bool(os.getenv("USE_TESTNET"), default=False)
    max_leverage = _to_float(os.getenv("MAX_LEVERAGE"), default=5.0)
    require_stop_loss_live = _to_bool(os.getenv("REQUIRE_STOP_LOSS_LIVE"), default=True)

    return AppConfig(
        api_key=api_key,
        api_secret=api_secret,
        use_testnet=use_testnet,
        max_leverage=max_leverage,
        require_stop_loss_live=require_stop_loss_live,
    )


def load_oauth_config() -> OAuthConfig:
    """Load OAuth configuration from environment variables."""
    load_dotenv()
    
    base_url = os.getenv("BASE_URL", "http://localhost:8010")
    
    return OAuthConfig(
        # Binance OAuth
        binance_client_id=os.getenv("BINANCE_CLIENT_ID"),
        binance_client_secret=os.getenv("BINANCE_CLIENT_SECRET"),
        binance_redirect_uri=f"{base_url}/api/exchanges/oauth/callback/binance",
        
        # Bybit OAuth
        bybit_client_id=os.getenv("BYBIT_CLIENT_ID"),
        bybit_client_secret=os.getenv("BYBIT_CLIENT_SECRET"),
        bybit_redirect_uri=f"{base_url}/api/exchanges/oauth/callback/bybit",
        
        # General
        base_url=base_url,
        encryption_key=os.getenv("ENCRYPTION_KEY"),
    )


def load_gemini_config() -> GeminiConfig:
    """Load Gemini AI configuration from environment variables."""
    load_dotenv()
    
    return GeminiConfig(
        api_key=os.getenv("GEMINI_API_KEY"),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-pro"),
        temperature=_to_float(os.getenv("GEMINI_TEMPERATURE"), default=0.7),
        max_tokens=int(os.getenv("GEMINI_MAX_TOKENS", "4096"))
    )


def ensure_live_confirmation(live_flag: bool, confirm_yes_flag: bool) -> None:
    """Gate that prevents accidental live trading without explicit consent.

    Live mode is allowed only if either CONFIRM=YES env var is set or --confirm-yes flag is provided.
    """
    if not live_flag:
        return

    env_confirm = os.getenv("CONFIRM", "").strip().upper()
    if confirm_yes_flag or env_confirm == "YES":
        return

    raise RuntimeError(
        "Live mode requested but not confirmed. Set CONFIRM=YES or pass --confirm-yes."
    )


@dataclass
class SupabaseConfig:
    """Supabase configuration for Edge Functions"""
    url: str
    key: str
    function_name: str = "ai-trading-signals"


def load_supabase_config() -> SupabaseConfig:
    """Load Supabase configuration."""
    load_dotenv()
    
    # Defaults from the Rust test file
    default_project_ref = "iqqmbzznwpheqiihnjhz"
    default_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlxcW1ienpud3BoZXFpaWhuamh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkwMDc5MDUsImV4cCI6MjA3NDU4MzkwNX0.qwk2MN2CnwybHKfQgXcpSTx4B5VPWTjnO7ZkGLxlr4c"
    
    project_ref = os.getenv("SUPABASE_PROJECT_REF", default_project_ref)
    key = os.getenv("SUPABASE_KEY", default_key)
    
    return SupabaseConfig(
        url=f"https://{project_ref}.supabase.co/functions/v1",
        key=key
    )


