"""
Bot Configuration Module
========================

Trading modes and system configuration.
"""

from .trading_modes import (
    TRADING_MODES,
    TradingMode,
    get_mode,
    get_mode_config_dict
)

# Re-export from bot/config.py (main config file)
# Import using importlib.util to avoid name collision
import importlib.util
import os
import sys

_bot_dir = os.path.dirname(os.path.dirname(__file__))
_config_py_path = os.path.join(_bot_dir, 'config.py')

if os.path.exists(_config_py_path):
    spec = importlib.util.spec_from_file_location("bot_config_module", _config_py_path)
    _config_module = importlib.util.module_from_spec(spec)
    # Register module in sys.modules to fix dataclass issue
    sys.modules["bot_config_module"] = _config_module
    spec.loader.exec_module(_config_module)
    
    # Re-export key items
    load_config = _config_module.load_config
    AppConfig = _config_module.AppConfig
    load_oauth_config = _config_module.load_oauth_config
    OAuthConfig = _config_module.OAuthConfig
    load_gemini_config = _config_module.load_gemini_config
    GeminiConfig = _config_module.GeminiConfig
    load_supabase_config = _config_module.load_supabase_config
    SupabaseConfig = _config_module.SupabaseConfig
    ensure_live_confirmation = _config_module.ensure_live_confirmation

__all__ = [
    # Trading modes
    'TRADING_MODES',
    'TradingMode', 
    'get_mode',
    'get_mode_config_dict',
    # App config
    'load_config',
    'AppConfig',
    'load_oauth_config',
    'OAuthConfig',
    'load_gemini_config',
    'GeminiConfig',
    'load_supabase_config',
    'SupabaseConfig',
    'ensure_live_confirmation',
]
