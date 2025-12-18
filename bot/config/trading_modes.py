"""
Trading Modes Configuration v1.0
================================

Different trading modes optimized for various market conditions and trading styles.
Created: 2025-12-14

Usage in auto_trader.py:
    from bot.config.trading_modes import TRADING_MODES, get_mode
    mode = get_mode('scalping')  # or 'day_trading', 'swing', 'conservative'
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class TradingMode:
    """Configuration for a specific trading mode."""
    
    # Time Settings
    max_hold_hours: float           # Maximum position hold time
    force_close_multiplier: float   # Force close after max_hold * this
    
    # Risk Settings
    default_sl_pct: float           # Default Stop Loss %
    default_tp_pct: float           # Default Take Profit %
    trailing_distance_pct: float    # Trailing stop distance %
    trailing_activation_pct: float  # Activate trailing after this % profit
    
    # Position Sizing
    max_position_pct: float         # Max position as % of capital
    max_concurrent_trades: int      # Maximum concurrent positions
    
    # Signal Settings
    min_confidence: float           # Minimum AI signal confidence
    signal_window_hours: float      # How old signals can be
    
    # Partial Take Profit
    enable_partial_tp: bool         # Enable partial TP
    partial_tp_levels: list         # TP levels [25%, 50%, 75%]
    
    # Scalping specific
    enable_quick_exit: bool         # Exit on small profit quickly
    quick_exit_profit_pct: float    # Exit if this profit reached quickly
    quick_exit_time_minutes: int    # "Quickly" = within these minutes
    
    # v1.2: Smart Break-Even
    enable_break_even: bool = True          # Move SL to entry after profit
    break_even_trigger_pct: float = 1.0     # Activate at this profit %
    break_even_buffer_pct: float = 0.1      # Buffer above entry
    
    # v1.2: Momentum Scalper
    enable_momentum_scalp: bool = False     # Exit at 50% of TP quickly
    momentum_scalp_pct: float = 50.0        # % of TP target to trigger
    momentum_scalp_minutes: int = 60        # Time window
    
    # v1.2: News Protection
    enable_news_protection: bool = False    # Auto-close before events
    news_close_minutes_before: int = 30     # Minutes before event
    
    # Description (with default to fix dataclass ordering)
    description: str = ""                   # Mode description


# =============================================================================
# TRADING MODES DEFINITIONS
# =============================================================================

TRADING_MODES: Dict[str, TradingMode] = {
    
    # =========================================================================
    # SCALPING MODE - Ultra short-term, many small trades
    # =========================================================================
    'scalping': TradingMode(
        max_hold_hours=1.0,              # Max 1 hour per trade
        force_close_multiplier=1.5,      # Force close after 1.5h
        
        default_sl_pct=1.5,              # Tight 1.5% SL
        default_tp_pct=2.0,              # Small 2% TP
        trailing_distance_pct=0.8,       # Very tight 0.8% trailing
        trailing_activation_pct=0.5,     # Activate early at 0.5%
        
        max_position_pct=5.0,            # Small positions
        max_concurrent_trades=10,        # Many small trades
        
        min_confidence=0.7,              # Higher confidence required
        signal_window_hours=0.25,        # Only 15-min old signals
        
        enable_partial_tp=False,         # No partial - all or nothing
        partial_tp_levels=[],
        
        enable_quick_exit=True,          # Quick exits enabled
        quick_exit_profit_pct=0.5,       # Exit at 0.5% profit
        quick_exit_time_minutes=5,       # If reached within 5 min
        
        # v1.2: New features for scalping
        enable_break_even=True,          # Yes - protect even small gains
        break_even_trigger_pct=0.5,      # Earlier trigger for scalping
        break_even_buffer_pct=0.05,      # Tighter buffer
        
        enable_momentum_scalp=True,      # YES - core scalping feature
        momentum_scalp_pct=50.0,         # Exit at 50% of TP
        momentum_scalp_minutes=60,       # Within 60 minutes
        
        enable_news_protection=True,     # Protect from volatility
        news_close_minutes_before=30,
        
        description="Ultra short-term scalping. Many small, quick trades with tight SL/TP."
    ),
    
    # =========================================================================
    # DAY TRADING MODE - Intraday positions, closed same day
    # =========================================================================
    'day_trading': TradingMode(
        max_hold_hours=6.0,              # Max 6 hours
        force_close_multiplier=1.5,      # Force close after 9h
        
        default_sl_pct=3.0,              # 3% SL
        default_tp_pct=5.0,              # 5% TP
        trailing_distance_pct=1.5,       # 1.5% trailing
        trailing_activation_pct=2.0,     # Activate at 2%
        
        max_position_pct=15.0,           # Medium positions
        max_concurrent_trades=5,         # Limited concurrent
        
        min_confidence=0.6,              # Standard confidence
        signal_window_hours=1.0,         # 1h old signals OK
        
        enable_partial_tp=True,          # Partial TP enabled
        partial_tp_levels=[0.33, 0.66],  # 33%, 66% levels
        
        enable_quick_exit=True,
        quick_exit_profit_pct=1.5,       # Exit at 1.5%
        quick_exit_time_minutes=30,      # Within 30 min
        
        # v1.2: New features
        enable_break_even=True,
        break_even_trigger_pct=1.0,      # Standard 1% trigger
        break_even_buffer_pct=0.1,
        
        enable_momentum_scalp=False,     # Not for day trading
        momentum_scalp_pct=50.0,
        momentum_scalp_minutes=60,
        
        enable_news_protection=True,     # Protect profits before news
        news_close_minutes_before=30,
        
        description="Intraday trading. Positions closed within the day."
    ),
    
    # =========================================================================
    # SWING MODE - Multi-day positions (DEFAULT)
    # =========================================================================
    'swing': TradingMode(
        max_hold_hours=12.0,             # Max 12 hours (default)
        force_close_multiplier=2.0,      # Force close after 24h
        default_sl_pct=5.0,              # 5% SL
        default_tp_pct=7.0,              # 7% TP
        trailing_distance_pct=2.0,       # 2% trailing
        trailing_activation_pct=3.0,     # Activate at 3%
        
        max_position_pct=20.0,           # Larger positions
        max_concurrent_trades=5,
        
        min_confidence=0.5,              # Standard confidence
        signal_window_hours=4.0,         # 4h old signals OK
        
        enable_partial_tp=True,
        partial_tp_levels=[0.25, 0.50, 0.75],
        
        enable_quick_exit=False,
        quick_exit_profit_pct=0,
        quick_exit_time_minutes=0,
        
        # v1.2: New features
        enable_break_even=True,
        break_even_trigger_pct=2.0,      # Higher threshold for swing
        break_even_buffer_pct=0.15,
        
        enable_momentum_scalp=False,     # Not for swing trading
        momentum_scalp_pct=50.0,
        momentum_scalp_minutes=60,
        
        enable_news_protection=False,    # Swing trades can ride out news
        news_close_minutes_before=30,
        
        description="Multi-day swing trading. Default mode with balanced risk/reward."
    ),
    
    # =========================================================================
    # CONSERVATIVE MODE - Safe, long-term positions
    # =========================================================================
    'conservative': TradingMode(
        max_hold_hours=48.0,             # Up to 2 days
        force_close_multiplier=2.0,      # Force close after 4 days
        
        default_sl_pct=7.0,              # Wide 7% SL
        default_tp_pct=12.0,             # Large 12% TP
        trailing_distance_pct=3.0,       # Wide 3% trailing
        trailing_activation_pct=5.0,     # Activate at 5%
        
        max_position_pct=10.0,           # Smaller positions
        max_concurrent_trades=3,         # Few concurrent
        
        min_confidence=0.75,             # High confidence required
        signal_window_hours=12.0,        # 12h old signals OK
        
        enable_partial_tp=True,
        partial_tp_levels=[0.30, 0.60, 0.90],
        
        enable_quick_exit=False,
        quick_exit_profit_pct=0,
        quick_exit_time_minutes=0,
        
        # v1.2: New features
        enable_break_even=True,
        break_even_trigger_pct=3.0,      # Very conservative trigger
        break_even_buffer_pct=0.2,
        
        enable_momentum_scalp=False,     # Not for conservative
        momentum_scalp_pct=50.0,
        momentum_scalp_minutes=60,
        
        enable_news_protection=False,    # Long-term, ride out news
        news_close_minutes_before=30,
        
        description="Conservative, low-risk trading. Larger TP targets, fewer trades."
    ),
    
    # =========================================================================
    # AGGRESSIVE MODE - High risk, high reward
    # =========================================================================
    'aggressive': TradingMode(
        max_hold_hours=4.0,              # Short hold
        force_close_multiplier=1.5,
        
        default_sl_pct=2.0,              # Tight 2% SL
        default_tp_pct=6.0,              # 6% TP (3:1 R:R)
        trailing_distance_pct=1.0,       # Tight 1% trailing
        trailing_activation_pct=1.5,     # Early activation
        
        max_position_pct=25.0,           # Large positions
        max_concurrent_trades=8,         # Many trades
        
        min_confidence=0.55,             # Lower threshold
        signal_window_hours=0.5,         # Fresh signals only
        
        enable_partial_tp=True,
        partial_tp_levels=[0.50],        # Only 50% level
        
        enable_quick_exit=True,
        quick_exit_profit_pct=2.0,
        quick_exit_time_minutes=15,
        
        # v1.2: New features
        enable_break_even=True,
        break_even_trigger_pct=1.0,      # Quick break-even
        break_even_buffer_pct=0.1,
        
        enable_momentum_scalp=True,      # Yes - capture quick moves
        momentum_scalp_pct=50.0,
        momentum_scalp_minutes=30,       # Faster window for aggressive
        
        enable_news_protection=True,     # Protect from volatility
        news_close_minutes_before=15,    # Closer to event
        
        description="Aggressive, high-risk trading. Larger positions, tighter stops."
    ),
}


def get_mode(mode_name: str) -> TradingMode:
    """Get trading mode configuration by name."""
    if mode_name not in TRADING_MODES:
        raise ValueError(f"Unknown trading mode: {mode_name}. Available: {list(TRADING_MODES.keys())}")
    return TRADING_MODES[mode_name]


def get_mode_config_dict(mode_name: str) -> Dict[str, Any]:
    """Get trading mode as dictionary (for JSON serialization)."""
    mode = get_mode(mode_name)
    return {
        'max_hold_hours': mode.max_hold_hours,
        'force_close_multiplier': mode.force_close_multiplier,
        'default_sl_pct': mode.default_sl_pct,
        'default_tp_pct': mode.default_tp_pct,
        'trailing_distance_pct': mode.trailing_distance_pct,
        'trailing_activation_pct': mode.trailing_activation_pct,
        'max_position_pct': mode.max_position_pct,
        'max_concurrent_trades': mode.max_concurrent_trades,
        'min_confidence': mode.min_confidence,
        'signal_window_hours': mode.signal_window_hours,
        'enable_partial_tp': mode.enable_partial_tp,
        'partial_tp_levels': mode.partial_tp_levels,
        'enable_quick_exit': mode.enable_quick_exit,
        'quick_exit_profit_pct': mode.quick_exit_profit_pct,
        'quick_exit_time_minutes': mode.quick_exit_time_minutes,
        'description': mode.description,
    }


# =============================================================================
# QUICK REFERENCE TABLE
# =============================================================================
"""
| Mode         | Max Hold | SL%  | TP%  | Trail% | Confidence | Description           |
|--------------|----------|------|------|--------|------------|-----------------------|
| scalping     | 1h       | 1.5% | 2%   | 0.8%   | 70%        | Ultra short, quick    |
| day_trading  | 6h       | 3%   | 5%   | 1.5%   | 60%        | Intraday, same day    |
| swing        | 12h      | 5%   | 7%   | 2%     | 50%        | Multi-day, balanced   |
| conservative | 48h      | 7%   | 12%  | 3%     | 75%        | Safe, long-term       |
| aggressive   | 4h       | 2%   | 6%   | 1%     | 55%        | High risk, high reward|
"""
