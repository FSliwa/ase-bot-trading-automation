"""
Symbol Normalizer - Unified symbol format across the entire system.

Ensures consistent symbol representation:
- Internal format: "BTC/USDT" (with slash)
- Base symbol: "BTC" (for DB storage)
- Exchange format: varies by exchange ("BTCUSDT", "BTC/USDT", "XBT/USD")
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedSymbol:
    """Immutable normalized symbol representation."""
    base: str           # BTC, ETH, SOL
    quote: str          # USDT, USDC, USD
    internal: str       # BTC/USDT (standard format)
    
    def __str__(self) -> str:
        return self.internal
    
    def __hash__(self) -> int:
        return hash(self.internal)


class SymbolNormalizer:
    """
    Centralizes symbol normalization for consistent representation.
    
    Usage:
        normalizer = SymbolNormalizer()
        symbol = normalizer.normalize("BTCUSDT")  # Returns NormalizedSymbol
        print(symbol.internal)  # "BTC/USDT"
        print(symbol.base)      # "BTC"
        
        # For specific exchange
        kraken_format = normalizer.to_exchange_format(symbol, "kraken")  # "XBT/USD"
    """
    
    # Quote currencies in order of preference
    QUOTE_CURRENCIES = ['USDT', 'USDC', 'USD', 'EUR', 'GBP', 'PLN', 'BUSD', 'DAI']
    
    # Exchange-specific symbol mappings
    EXCHANGE_MAPPINGS = {
        'kraken': {
            'BTC': 'XBT',   # Kraken uses XBT for Bitcoin
            'DOGE': 'XDG',
        },
        'binance': {},
        'bybit': {},
    }
    
    # Reverse mappings (exchange -> standard)
    REVERSE_MAPPINGS = {
        'kraken': {
            'XBT': 'BTC',
            'XDG': 'DOGE',
        }
    }
    
    # Quote currency mappings per exchange
    EXCHANGE_QUOTE_MAPPINGS = {
        'kraken': {
            'USD': 'USD',
            'USDT': 'USDT',
            'USDC': 'USDC',
            'EUR': 'EUR',
            # Kraken sometimes uses Z prefix for fiat
            'ZUSD': 'USD',
            'ZEUR': 'EUR',
        }
    }
    
    def __init__(self, default_quote: str = 'USDT'):
        self.default_quote = default_quote
        self._cache: Dict[str, NormalizedSymbol] = {}
    
    @lru_cache(maxsize=1000)
    def normalize(self, symbol: str, exchange: Optional[str] = None) -> NormalizedSymbol:
        """
        Normalize any symbol format to standard internal representation.
        
        Args:
            symbol: Input symbol in any format ("BTCUSDT", "BTC/USDT", "BTC", "XBT/USD")
            exchange: Optional exchange name for exchange-specific conversions
            
        Returns:
            NormalizedSymbol with base, quote, and internal format
        """
        if not symbol:
            raise ValueError("Symbol cannot be empty")
        
        symbol = symbol.strip().upper()
        
        # Check cache first
        cache_key = f"{symbol}:{exchange or ''}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        base, quote = self._parse_symbol(symbol, exchange)
        
        # Apply reverse mapping if from specific exchange
        if exchange and exchange in self.REVERSE_MAPPINGS:
            base = self.REVERSE_MAPPINGS[exchange].get(base, base)
        
        # Use default quote if not detected
        if not quote:
            quote = self.default_quote
        
        result = NormalizedSymbol(
            base=base,
            quote=quote,
            internal=f"{base}/{quote}"
        )
        
        self._cache[cache_key] = result
        return result
    
    def _parse_symbol(self, symbol: str, exchange: Optional[str] = None) -> Tuple[str, str]:
        """Parse symbol into base and quote components."""
        
        # Format 1: "BTC/USDT" - with slash
        if '/' in symbol:
            parts = symbol.split('/')
            return parts[0], parts[1] if len(parts) > 1 else ''
        
        # Format 2: "BTCUSDT" - concatenated
        for quote in self.QUOTE_CURRENCIES:
            if symbol.endswith(quote):
                return symbol[:-len(quote)], quote
        
        # Handle Kraken Z-prefix quotes
        if exchange == 'kraken':
            for zquote in ['ZUSD', 'ZEUR', 'ZGBP']:
                if symbol.endswith(zquote):
                    base = symbol[:-len(zquote)]
                    quote = zquote[1:]  # Remove Z prefix
                    return base, quote
        
        # Format 3: Just base symbol "BTC"
        return symbol, ''
    
    def to_exchange_format(self, symbol: NormalizedSymbol, exchange: str) -> str:
        """
        Convert normalized symbol to exchange-specific format.
        
        Args:
            symbol: NormalizedSymbol instance
            exchange: Exchange name ('binance', 'kraken', 'bybit', etc.)
            
        Returns:
            Exchange-specific symbol string
        """
        base = symbol.base
        quote = symbol.quote
        
        # Apply exchange-specific base mappings
        if exchange in self.EXCHANGE_MAPPINGS:
            base = self.EXCHANGE_MAPPINGS[exchange].get(base, base)
        
        # Exchange-specific format
        if exchange == 'binance':
            # Binance uses concatenated format: "BTCUSDT"
            return f"{base}{quote}"
        elif exchange == 'kraken':
            # Kraken uses slash format: "XBT/USD"
            return f"{base}/{quote}"
        elif exchange == 'bybit':
            # Bybit uses concatenated: "BTCUSDT"
            return f"{base}{quote}"
        else:
            # Default: slash format
            return f"{base}/{quote}"
    
    def from_exchange_format(self, symbol: str, exchange: str) -> NormalizedSymbol:
        """
        Convert exchange-specific symbol to normalized format.
        
        Args:
            symbol: Exchange-specific symbol
            exchange: Exchange name
            
        Returns:
            NormalizedSymbol
        """
        return self.normalize(symbol, exchange)
    
    def are_same_symbol(self, symbol1: str, symbol2: str, exchange: Optional[str] = None) -> bool:
        """
        Check if two symbol strings represent the same trading pair.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            exchange: Optional exchange for context
            
        Returns:
            True if symbols are equivalent
        """
        try:
            norm1 = self.normalize(symbol1, exchange)
            norm2 = self.normalize(symbol2, exchange)
            return norm1.base == norm2.base and norm1.quote == norm2.quote
        except ValueError:
            return False
    
    def get_base_symbol(self, symbol: str, exchange: Optional[str] = None) -> str:
        """Extract base currency from any symbol format."""
        return self.normalize(symbol, exchange).base
    
    def get_quote_symbol(self, symbol: str, exchange: Optional[str] = None) -> str:
        """Extract quote currency from any symbol format."""
        return self.normalize(symbol, exchange).quote


# Global singleton instance
_normalizer: Optional[SymbolNormalizer] = None


def get_symbol_normalizer(default_quote: str = 'USDT') -> SymbolNormalizer:
    """Get or create the global SymbolNormalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = SymbolNormalizer(default_quote)
    return _normalizer


def normalize_symbol(symbol: str, exchange: Optional[str] = None) -> str:
    """
    Convenience function to normalize a symbol to internal format.
    
    Args:
        symbol: Any symbol format
        exchange: Optional exchange name
        
    Returns:
        Internal format string "BASE/QUOTE"
    """
    return get_symbol_normalizer().normalize(symbol, exchange).internal


def to_exchange_format(symbol: str, exchange: str) -> str:
    """
    Convenience function to convert symbol to exchange format.
    
    Args:
        symbol: Any symbol format
        exchange: Target exchange name
        
    Returns:
        Exchange-specific symbol format
    """
    normalizer = get_symbol_normalizer()
    normalized = normalizer.normalize(symbol)
    return normalizer.to_exchange_format(normalized, exchange)


def get_base(symbol: str) -> str:
    """Extract base currency from symbol."""
    return get_symbol_normalizer().get_base_symbol(symbol)


def get_quote(symbol: str) -> str:
    """Extract quote currency from symbol."""
    return get_symbol_normalizer().get_quote_symbol(symbol)
