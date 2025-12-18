
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from bot.logging_setup import get_logger

logger = get_logger("technical_analysis")

class TechnicalAnalyzer:
    """
    Advanced Technical Analysis engine using Pandas.
    Calculates RSI, MACD, Bollinger Bands, ATR, and other indicators.
    """

    def __init__(self):
        pass

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """Calculate MACD, Signal line, and Histogram."""
        exp1 = prices.ewm(span=fast, adjust=False).mean()
        exp2 = prices.ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line
        
        return pd.DataFrame({
            'macd': macd,
            'signal': signal_line,
            'histogram': histogram
        })

    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
        """Calculate Bollinger Bands."""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return pd.DataFrame({
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        })

    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr

    def analyze_ohlcv(self, ohlcv_data: List[List[float]]) -> Dict[str, Any]:
        """
        Analyze OHLCV data and return latest indicators.
        Expected OHLCV format: [[timestamp, open, high, low, close, volume], ...]
        """
        if not ohlcv_data or len(ohlcv_data) < 30:
            logger.warning("Insufficient OHLCV data for analysis")
            return {}

        try:
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            
            # Calculate Indicators
            rsi = self.calculate_rsi(df['close'])
            macd = self.calculate_macd(df['close'])
            bb = self.calculate_bollinger_bands(df['close'])
            atr = self.calculate_atr(df['high'], df['low'], df['close'])
            
            # Get latest values
            latest = {
                'rsi': float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0,
                'macd': {
                    'value': float(macd['macd'].iloc[-1]),
                    'signal': float(macd['signal'].iloc[-1]),
                    'histogram': float(macd['histogram'].iloc[-1])
                },
                'bb': {
                    'upper': float(bb['upper'].iloc[-1]),
                    'middle': float(bb['middle'].iloc[-1]),
                    'lower': float(bb['lower'].iloc[-1]),
                    'percent_b': float((df['close'].iloc[-1] - bb['lower'].iloc[-1]) / (bb['upper'].iloc[-1] - bb['lower'].iloc[-1])) if (bb['upper'].iloc[-1] - bb['lower'].iloc[-1]) != 0 else 0.5
                },
                'atr': float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0,
                'sma_50': float(df['close'].rolling(window=50).mean().iloc[-1]) if len(df) >= 50 else 0.0,
                'sma_200': float(df['close'].rolling(window=200).mean().iloc[-1]) if len(df) >= 200 else 0.0
            }
            
            return latest
            
        except Exception as e:
            logger.error(f"Error in technical analysis: {e}")
            return {}
