"""
Enhanced Technical Analysis Module
Używa TA-Lib, pandas-ta i custom indicators dla lepszych sygnałów tradingowych
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio

# Try to import TA-Lib - fallback to pandas_ta if not available
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logging.warning("TA-Lib not available, falling back to pandas_ta")

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logging.warning("pandas_ta not available")

logger = logging.getLogger(__name__)

@dataclass
class TechnicalSignal:
    indicator: str
    signal: str  # 'BUY', 'SELL', 'HOLD'
    strength: float  # 0-1
    value: float
    timestamp: datetime
    metadata: Dict[str, Any] = None

@dataclass
class MarketRegime:
    regime: str  # 'TRENDING', 'RANGING', 'VOLATILE', 'CALM'
    confidence: float  # 0-1
    indicators: Dict[str, float]
    timestamp: datetime

class EnhancedTechnicalAnalysis:
    def __init__(self):
        self.indicators_config = {
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'bb_period': 20,
            'bb_std': 2,
            'stoch_k': 14,
            'stoch_d': 3,
            'adx_period': 14,
            'atr_period': 14
        }
    
    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Oblicza wszystkie wskaźniki techniczne"""
        if df.empty or len(df) < 50:
            return df
        
        result_df = df.copy()
        
        # Podstawowe wskaźniki cenowe
        result_df = self._add_price_indicators(result_df)
        
        # Wskaźniki momentum
        result_df = self._add_momentum_indicators(result_df)
        
        # Wskaźniki trendu
        result_df = self._add_trend_indicators(result_df)
        
        # Wskaźniki volatilności
        result_df = self._add_volatility_indicators(result_df)
        
        # Wskaźniki volume
        result_df = self._add_volume_indicators(result_df)
        
        # Custom indicators
        result_df = self._add_custom_indicators(result_df)
        
        return result_df
    
    def _add_price_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Dodaje wskaźniki cenowe"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        if TALIB_AVAILABLE:
            # Moving Averages
            df['sma_10'] = talib.SMA(close, timeperiod=10)
            df['sma_20'] = talib.SMA(close, timeperiod=20)
            df['sma_50'] = talib.SMA(close, timeperiod=50)
            df['sma_200'] = talib.SMA(close, timeperiod=200)
            df['ema_12'] = talib.EMA(close, timeperiod=12)
            df['ema_26'] = talib.EMA(close, timeperiod=26)
            
            # Pivot Points
            df['pivot'] = (high + low + close) / 3
            df['r1'] = 2 * df['pivot'] - low
            df['s1'] = 2 * df['pivot'] - high
            df['r2'] = df['pivot'] + (high - low)
            df['s2'] = df['pivot'] - (high - low)
        
        elif PANDAS_TA_AVAILABLE:
            # Fallback to pandas_ta
            df.ta.sma(length=10, append=True)
            df.ta.sma(length=20, append=True)
            df.ta.sma(length=50, append=True)
            df.ta.sma(length=200, append=True)
            df.ta.ema(length=12, append=True)
            df.ta.ema(length=26, append=True)
        
        return df
    
    def _add_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Dodaje wskaźniki momentum"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        if TALIB_AVAILABLE:
            # RSI
            df['rsi'] = talib.RSI(close, timeperiod=self.indicators_config['rsi_period'])
            
            # MACD
            macd, macd_signal, macd_hist = talib.MACD(
                close,
                fastperiod=self.indicators_config['macd_fast'],
                slowperiod=self.indicators_config['macd_slow'],
                signalperiod=self.indicators_config['macd_signal']
            )
            df['macd'] = macd
            df['macd_signal'] = macd_signal
            df['macd_histogram'] = macd_hist
            
            # Stochastic
            stoch_k, stoch_d = talib.STOCH(
                high, low, close,
                fastk_period=self.indicators_config['stoch_k'],
                slowk_period=self.indicators_config['stoch_d'],
                slowd_period=self.indicators_config['stoch_d']
            )
            df['stoch_k'] = stoch_k
            df['stoch_d'] = stoch_d
            
            # Williams %R
            df['williams_r'] = talib.WILLR(high, low, close, timeperiod=14)
            
            # Commodity Channel Index
            df['cci'] = talib.CCI(high, low, close, timeperiod=20)
            
            # Rate of Change
            df['roc'] = talib.ROC(close, timeperiod=10)
        
        elif PANDAS_TA_AVAILABLE:
            df.ta.rsi(length=14, append=True)
            df.ta.macd(append=True)
            df.ta.stoch(append=True)
            df.ta.willr(append=True)
            df.ta.cci(append=True)
            df.ta.roc(append=True)
        
        return df
    
    def _add_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Dodaje wskaźniki trendu"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        if TALIB_AVAILABLE:
            # ADX - Average Directional Index
            df['adx'] = talib.ADX(high, low, close, timeperiod=self.indicators_config['adx_period'])
            df['plus_di'] = talib.PLUS_DI(high, low, close, timeperiod=14)
            df['minus_di'] = talib.MINUS_DI(high, low, close, timeperiod=14)
            
            # Parabolic SAR
            df['sar'] = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
            
            # Aroon
            aroon_down, aroon_up = talib.AROON(high, low, timeperiod=14)
            df['aroon_up'] = aroon_up
            df['aroon_down'] = aroon_down
            
            # TRIX
            df['trix'] = talib.TRIX(close, timeperiod=14)
        
        elif PANDAS_TA_AVAILABLE:
            df.ta.adx(append=True)
            df.ta.psar(append=True)
            df.ta.aroon(append=True)
            df.ta.trix(append=True)
        
        return df
    
    def _add_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Dodaje wskaźniki volatilności"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        if TALIB_AVAILABLE:
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = talib.BBANDS(
                close,
                timeperiod=self.indicators_config['bb_period'],
                nbdevup=self.indicators_config['bb_std'],
                nbdevdn=self.indicators_config['bb_std']
            )
            df['bb_upper'] = bb_upper
            df['bb_middle'] = bb_middle
            df['bb_lower'] = bb_lower
            df['bb_width'] = (bb_upper - bb_lower) / bb_middle
            df['bb_position'] = (close - bb_lower) / (bb_upper - bb_lower)
            
            # Average True Range
            df['atr'] = talib.ATR(high, low, close, timeperiod=self.indicators_config['atr_period'])
            
            # Normalized ATR
            df['natr'] = talib.NATR(high, low, close, timeperiod=14)
            
            # True Range
            df['trange'] = talib.TRANGE(high, low, close)
        
        elif PANDAS_TA_AVAILABLE:
            df.ta.bbands(append=True)
            df.ta.atr(append=True)
            df.ta.natr(append=True)
            df.ta.true_range(append=True)
        
        return df
    
    def _add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Dodaje wskaźniki volume"""
        if 'volume' not in df.columns:
            return df
        
        close = df['close'].values
        volume = df['volume'].values
        high = df['high'].values
        low = df['low'].values
        
        if TALIB_AVAILABLE:
            # On-Balance Volume
            df['obv'] = talib.OBV(close, volume)
            
            # Accumulation/Distribution Line
            df['ad'] = talib.AD(high, low, close, volume)
            
            # Chaikin A/D Oscillator
            df['adosc'] = talib.ADOSC(high, low, close, volume, fastperiod=3, slowperiod=10)
        
        elif PANDAS_TA_AVAILABLE:
            df.ta.obv(append=True)
            df.ta.ad(append=True)
            df.ta.adosc(append=True)
        
        # Custom volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        return df
    
    def _add_custom_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Dodaje custom wskaźniki"""
        # Volatility-adjusted momentum
        if 'rsi' in df.columns and 'atr' in df.columns:
            df['va_momentum'] = df['rsi'] * (1 + df['atr'] / df['close'])
        
        # Trend strength indicator
        if all(col in df.columns for col in ['sma_10', 'sma_20', 'sma_50']):
            df['trend_strength'] = (
                (df['sma_10'] > df['sma_20']).astype(int) +
                (df['sma_20'] > df['sma_50']).astype(int) +
                (df['close'] > df['sma_10']).astype(int)
            ) / 3
        
        # Market pressure indicator
        if all(col in df.columns for col in ['rsi', 'stoch_k', 'williams_r']):
            df['market_pressure'] = (
                (df['rsi'] - 50) / 50 +
                (df['stoch_k'] - 50) / 50 +
                (df['williams_r'] + 50) / 50
            ) / 3
        
        # Volatility regime
        if 'atr' in df.columns:
            atr_mean = df['atr'].rolling(window=50).mean()
            atr_std = df['atr'].rolling(window=50).std()
            df['volatility_regime'] = (df['atr'] - atr_mean) / atr_std
        
        return df
    
    def generate_signals(self, df: pd.DataFrame) -> List[TechnicalSignal]:
        """Generuje sygnały trading na podstawie wskaźników"""
        signals = []
        
        if df.empty or len(df) < 2:
            return signals
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # RSI signals
        if 'rsi' in df.columns:
            rsi_signal = self._analyze_rsi(latest, previous)
            if rsi_signal:
                signals.append(rsi_signal)
        
        # MACD signals
        if all(col in df.columns for col in ['macd', 'macd_signal']):
            macd_signal = self._analyze_macd(latest, previous)
            if macd_signal:
                signals.append(macd_signal)
        
        # Bollinger Bands signals
        if all(col in df.columns for col in ['bb_upper', 'bb_lower', 'close']):
            bb_signal = self._analyze_bollinger_bands(latest, previous)
            if bb_signal:
                signals.append(bb_signal)
        
        # Moving Average signals
        if all(col in df.columns for col in ['sma_10', 'sma_20']):
            ma_signal = self._analyze_moving_averages(latest, previous)
            if ma_signal:
                signals.append(ma_signal)
        
        # Volume signals
        if 'volume_ratio' in df.columns:
            volume_signal = self._analyze_volume(latest, previous)
            if volume_signal:
                signals.append(volume_signal)
        
        return signals
    
    def _analyze_rsi(self, latest: pd.Series, previous: pd.Series) -> Optional[TechnicalSignal]:
        """Analizuje sygnały RSI"""
        rsi = latest['rsi']
        prev_rsi = previous['rsi']
        
        if pd.isna(rsi) or pd.isna(prev_rsi):
            return None
        
        # Oversold/Overbought conditions
        if rsi < 30 and prev_rsi >= 30:
            return TechnicalSignal(
                indicator='RSI',
                signal='BUY',
                strength=min((30 - rsi) / 10, 1.0),
                value=rsi,
                timestamp=datetime.now(),
                metadata={'condition': 'oversold_entry'}
            )
        elif rsi > 70 and prev_rsi <= 70:
            return TechnicalSignal(
                indicator='RSI',
                signal='SELL',
                strength=min((rsi - 70) / 10, 1.0),
                value=rsi,
                timestamp=datetime.now(),
                metadata={'condition': 'overbought_entry'}
            )
        
        return None
    
    def _analyze_macd(self, latest: pd.Series, previous: pd.Series) -> Optional[TechnicalSignal]:
        """Analizuje sygnały MACD"""
        macd = latest['macd']
        macd_signal = latest['macd_signal']
        prev_macd = previous['macd']
        prev_signal = previous['macd_signal']
        
        if any(pd.isna(x) for x in [macd, macd_signal, prev_macd, prev_signal]):
            return None
        
        # MACD crossover
        if macd > macd_signal and prev_macd <= prev_signal:
            strength = min(abs(macd - macd_signal) / abs(macd), 1.0)
            return TechnicalSignal(
                indicator='MACD',
                signal='BUY',
                strength=strength,
                value=macd - macd_signal,
                timestamp=datetime.now(),
                metadata={'condition': 'bullish_crossover'}
            )
        elif macd < macd_signal and prev_macd >= prev_signal:
            strength = min(abs(macd - macd_signal) / abs(macd), 1.0)
            return TechnicalSignal(
                indicator='MACD',
                signal='SELL',
                strength=strength,
                value=macd - macd_signal,
                timestamp=datetime.now(),
                metadata={'condition': 'bearish_crossover'}
            )
        
        return None
    
    def _analyze_bollinger_bands(self, latest: pd.Series, previous: pd.Series) -> Optional[TechnicalSignal]:
        """Analizuje sygnały Bollinger Bands"""
        close = latest['close']
        bb_upper = latest['bb_upper']
        bb_lower = latest['bb_lower']
        prev_close = previous['close']
        
        if any(pd.isna(x) for x in [close, bb_upper, bb_lower, prev_close]):
            return None
        
        # Bounce from bands
        if close > bb_lower and prev_close <= bb_lower:
            return TechnicalSignal(
                indicator='BB',
                signal='BUY',
                strength=0.7,
                value=close,
                timestamp=datetime.now(),
                metadata={'condition': 'bounce_from_lower_band'}
            )
        elif close < bb_upper and prev_close >= bb_upper:
            return TechnicalSignal(
                indicator='BB',
                signal='SELL',
                strength=0.7,
                value=close,
                timestamp=datetime.now(),
                metadata={'condition': 'rejection_from_upper_band'}
            )
        
        return None
    
    def _analyze_moving_averages(self, latest: pd.Series, previous: pd.Series) -> Optional[TechnicalSignal]:
        """Analizuje sygnały Moving Average"""
        sma_10 = latest['sma_10']
        sma_20 = latest['sma_20']
        prev_sma_10 = previous['sma_10']
        prev_sma_20 = previous['sma_20']
        
        if any(pd.isna(x) for x in [sma_10, sma_20, prev_sma_10, prev_sma_20]):
            return None
        
        # Golden/Death cross
        if sma_10 > sma_20 and prev_sma_10 <= prev_sma_20:
            return TechnicalSignal(
                indicator='MA_CROSS',
                signal='BUY',
                strength=0.8,
                value=sma_10 - sma_20,
                timestamp=datetime.now(),
                metadata={'condition': 'golden_cross'}
            )
        elif sma_10 < sma_20 and prev_sma_10 >= prev_sma_20:
            return TechnicalSignal(
                indicator='MA_CROSS',
                signal='SELL',
                strength=0.8,
                value=sma_10 - sma_20,
                timestamp=datetime.now(),
                metadata={'condition': 'death_cross'}
            )
        
        return None
    
    def _analyze_volume(self, latest: pd.Series, previous: pd.Series) -> Optional[TechnicalSignal]:
        """Analizuje sygnały volume"""
        if 'volume_ratio' not in latest:
            return None
        
        volume_ratio = latest['volume_ratio']
        close = latest['close']
        prev_close = previous['close']
        
        if pd.isna(volume_ratio):
            return None
        
        price_change = (close - prev_close) / prev_close
        
        # High volume with price movement
        if volume_ratio > 2.0 and abs(price_change) > 0.02:
            signal = 'BUY' if price_change > 0 else 'SELL'
            return TechnicalSignal(
                indicator='VOLUME',
                signal=signal,
                strength=min(volume_ratio / 3, 1.0),
                value=volume_ratio,
                timestamp=datetime.now(),
                metadata={
                    'condition': 'high_volume_breakout',
                    'price_change': price_change
                }
            )
        
        return None
    
    def detect_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        """Wykrywa reżim rynkowy"""
        if df.empty or len(df) < 50:
            return MarketRegime('UNKNOWN', 0.0, {}, datetime.now())
        
        indicators = {}
        
        # Trend strength
        if 'adx' in df.columns:
            adx_value = df['adx'].iloc[-1]
            indicators['adx'] = adx_value
        else:
            adx_value = 25  # Default neutral
        
        # Volatility
        if 'atr' in df.columns:
            atr_current = df['atr'].iloc[-1]
            atr_mean = df['atr'].tail(20).mean()
            volatility_ratio = atr_current / atr_mean if atr_mean > 0 else 1
            indicators['volatility_ratio'] = volatility_ratio
        else:
            volatility_ratio = 1.0
        
        # Price movement
        price_std = df['close'].tail(20).std()
        price_mean = df['close'].tail(20).mean()
        price_volatility = price_std / price_mean if price_mean > 0 else 0
        indicators['price_volatility'] = price_volatility
        
        # Determine regime
        if adx_value > 25 and volatility_ratio < 1.2:
            regime = 'TRENDING'
            confidence = min(adx_value / 50, 1.0)
        elif adx_value < 20 and volatility_ratio < 0.8:
            regime = 'RANGING'
            confidence = min((25 - adx_value) / 25, 1.0)
        elif volatility_ratio > 1.5:
            regime = 'VOLATILE'
            confidence = min(volatility_ratio / 2, 1.0)
        else:
            regime = 'CALM'
            confidence = 0.5
        
        return MarketRegime(
            regime=regime,
            confidence=confidence,
            indicators=indicators,
            timestamp=datetime.now()
        )
    
    def calculate_support_resistance(self, df: pd.DataFrame, window: int = 20) -> Dict[str, List[float]]:
        """Oblicza poziomy wsparcia i oporu"""
        if df.empty or len(df) < window:
            return {'support': [], 'resistance': []}
        
        highs = df['high'].rolling(window=window, center=True).max()
        lows = df['low'].rolling(window=window, center=True).min()
        
        # Find local maxima and minima
        resistance_levels = []
        support_levels = []
        
        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == highs.iloc[i]:
                resistance_levels.append(df['high'].iloc[i])
            if df['low'].iloc[i] == lows.iloc[i]:
                support_levels.append(df['low'].iloc[i])
        
        # Remove duplicates and sort
        resistance_levels = sorted(list(set(resistance_levels)), reverse=True)[:5]
        support_levels = sorted(list(set(support_levels)))[:5]
        
        return {
            'resistance': resistance_levels,
            'support': support_levels
        }

# Singleton instance
_technical_analyzer = None

def get_technical_analyzer() -> EnhancedTechnicalAnalysis:
    global _technical_analyzer
    if _technical_analyzer is None:
        _technical_analyzer = EnhancedTechnicalAnalysis()
    return _technical_analyzer
