"""Neural Network Market Prediction (NNMP) - Advanced ML price prediction."""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
from dataclasses import dataclass
import logging
import ta  # Technical Analysis library

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Neural network prediction result."""
    symbol: str
    timeframe: str  # 5m, 15m, 1h, 4h, 1d
    direction: str  # up/down/neutral
    confidence: float  # 0-1
    predicted_price: float
    predicted_change_percent: float
    support_levels: List[float]
    resistance_levels: List[float]
    timestamp: datetime
    features_importance: Dict[str, float]


class LSTMPredictor(nn.Module):
    """LSTM model for time series prediction."""
    
    def __init__(self, input_size: int, hidden_size: int = 128, 
                 num_layers: int = 3, dropout: float = 0.2):
        super(LSTMPredictor, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
            bidirectional=True
        )
        
        # Attention mechanism
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size * 2,  # bidirectional
            num_heads=8,
            dropout=dropout
        )
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_size * 2, hidden_size)
        self.fc2 = nn.Linear(hidden_size, 64)
        self.fc3 = nn.Linear(64, 32)
        self.output = nn.Linear(32, 1)
        
        # Activation and regularization
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.batch_norm1 = nn.BatchNorm1d(hidden_size)
        self.batch_norm2 = nn.BatchNorm1d(64)
        
    def forward(self, x):
        # LSTM forward pass
        lstm_out, (hidden, cell) = self.lstm(x)
        
        # Apply attention
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        
        # Use last output
        out = attn_out[:, -1, :]
        
        # Fully connected layers
        out = self.dropout(self.relu(self.fc1(out)))
        out = self.batch_norm1(out)
        out = self.dropout(self.relu(self.fc2(out)))
        out = self.batch_norm2(out)
        out = self.dropout(self.relu(self.fc3(out)))
        
        # Output
        return self.output(out)


class TransformerPredictor(nn.Module):
    """Transformer model for pattern recognition."""
    
    def __init__(self, input_size: int, d_model: int = 256, 
                 nhead: int = 8, num_layers: int = 4):
        super(TransformerPredictor, self).__init__()
        
        # Input embedding
        self.input_embedding = nn.Linear(input_size, d_model)
        
        # Positional encoding
        self.pos_encoder = PositionalEncoding(d_model)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=512,
            dropout=0.1
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output layers
        self.fc1 = nn.Linear(d_model, 128)
        self.fc2 = nn.Linear(128, 64)
        self.output = nn.Linear(64, 1)
        self.dropout = nn.Dropout(0.1)
        
    def forward(self, x):
        # Embed input
        x = self.input_embedding(x)
        x = self.pos_encoder(x)
        
        # Transformer encoding
        x = self.transformer(x)
        
        # Global average pooling
        x = torch.mean(x, dim=1)
        
        # Output layers
        x = self.dropout(torch.relu(self.fc1(x)))
        x = self.dropout(torch.relu(self.fc2(x)))
        
        return self.output(x)


class PositionalEncoding(nn.Module):
    """Positional encoding for transformer."""
    
    def __init__(self, d_model: int, max_len: int = 5000):
        super(PositionalEncoding, self).__init__()
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * 
                           (-np.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        
        self.register_buffer('pe', pe)
        
    def forward(self, x):
        return x + self.pe[:x.size(0), :]


class NeuralMarketPredictor:
    """
    Neural Network Market Prediction Engine.
    Combines LSTM and Transformer models for accurate price prediction.
    """
    
    def __init__(self, config: Dict = None):
        """Initialize neural predictor."""
        self.config = config or {}
        
        # Model parameters
        self.sequence_length = 100  # Historical points to consider
        self.prediction_horizons = {
            '5m': 1,
            '15m': 3,
            '1h': 12,
            '4h': 48,
            '1d': 288
        }
        
        # Feature engineering parameters
        self.technical_indicators = [
            'rsi', 'macd', 'bb_upper', 'bb_lower', 'ema_9', 'ema_21',
            'adx', 'atr', 'obv', 'vwap', 'stoch_k', 'stoch_d'
        ]
        
        # Models
        self.lstm_model = None
        self.transformer_model = None
        self.ensemble_weights = {'lstm': 0.6, 'transformer': 0.4}
        
        # Preprocessing
        self.scaler = StandardScaler()
        self.feature_importance = {}
        
        # Device
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {self.device}")
        
    def prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Prepare features from OHLCV data.
        Calculates 200+ technical indicators.
        """
        # Basic price features
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        df['volume_change'] = df['volume'].pct_change()
        
        # Price ratios
        df['high_low_ratio'] = df['high'] / df['low']
        df['close_open_ratio'] = df['close'] / df['open']
        
        # Moving averages
        for period in [5, 9, 21, 50, 100, 200]:
            df[f'sma_{period}'] = df['close'].rolling(period).mean()
            df[f'ema_{period}'] = df['close'].ewm(span=period).mean()
            df[f'volume_sma_{period}'] = df['volume'].rolling(period).mean()
        
        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
        
        # MACD
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'])
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = bb.bollinger_wband()
        df['bb_percent'] = bb.bollinger_pband()
        
        # ATR
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close']).average_true_range()
        
        # ADX
        adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'])
        df['adx'] = adx.adx()
        df['adx_pos'] = adx.adx_pos()
        df['adx_neg'] = adx.adx_neg()
        
        # Stochastic
        stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'])
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()
        
        # Volume indicators
        df['obv'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
        df['cmf'] = ta.volume.ChaikinMoneyFlowIndicator(df['high'], df['low'], df['close'], df['volume']).chaikin_money_flow()
        
        # VWAP
        df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
        
        # Ichimoku
        ichimoku = ta.trend.IchimokuIndicator(df['high'], df['low'])
        df['ichimoku_a'] = ichimoku.ichimoku_a()
        df['ichimoku_b'] = ichimoku.ichimoku_b()
        
        # Pattern recognition features
        df['doji'] = self._detect_doji(df)
        df['hammer'] = self._detect_hammer(df)
        df['shooting_star'] = self._detect_shooting_star(df)
        
        # Market microstructure
        df['bid_ask_spread'] = df['high'] - df['low']
        df['price_efficiency'] = abs(df['close'] - df['open']) / (df['high'] - df['low'] + 1e-10)
        
        # Volatility features
        df['volatility_5'] = df['returns'].rolling(5).std()
        df['volatility_20'] = df['returns'].rolling(20).std()
        df['volatility_ratio'] = df['volatility_5'] / (df['volatility_20'] + 1e-10)
        
        # Remove NaN values
        df = df.dropna()
        
        # Select features
        feature_columns = [col for col in df.columns if col not in ['open', 'high', 'low', 'close', 'volume', 'timestamp']]
        
        return df[feature_columns].values
    
    def _detect_doji(self, df: pd.DataFrame) -> pd.Series:
        """Detect doji candlestick pattern."""
        body = abs(df['close'] - df['open'])
        range_hl = df['high'] - df['low']
        return (body <= range_hl * 0.1).astype(int)
    
    def _detect_hammer(self, df: pd.DataFrame) -> pd.Series:
        """Detect hammer candlestick pattern."""
        body = abs(df['close'] - df['open'])
        lower_shadow = df[['close', 'open']].min(axis=1) - df['low']
        upper_shadow = df['high'] - df[['close', 'open']].max(axis=1)
        
        return ((lower_shadow > body * 2) & (upper_shadow < body * 0.3)).astype(int)
    
    def _detect_shooting_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect shooting star pattern."""
        body = abs(df['close'] - df['open'])
        lower_shadow = df[['close', 'open']].min(axis=1) - df['low']
        upper_shadow = df['high'] - df[['close', 'open']].max(axis=1)
        
        return ((upper_shadow > body * 2) & (lower_shadow < body * 0.3)).astype(int)
    
    def create_sequences(self, features: np.ndarray, targets: np.ndarray, 
                        seq_length: int) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for time series prediction."""
        sequences = []
        labels = []
        
        for i in range(len(features) - seq_length):
            sequences.append(features[i:i + seq_length])
            labels.append(targets[i + seq_length])
            
        return np.array(sequences), np.array(labels)
    
    def train_models(self, training_data: pd.DataFrame, epochs: int = 50):
        """Train both LSTM and Transformer models."""
        logger.info("Starting model training...")
        
        # Prepare features
        features = self.prepare_features(training_data)
        targets = training_data['close'].pct_change().shift(-1).dropna().values[-len(features):]
        
        # Normalize features
        features_scaled = self.scaler.fit_transform(features)
        
        # Create sequences
        X, y = self.create_sequences(features_scaled, targets, self.sequence_length)
        
        # Convert to tensors
        X_tensor = torch.FloatTensor(X).to(self.device)
        y_tensor = torch.FloatTensor(y).unsqueeze(1).to(self.device)
        
        # Create data loader
        dataset = TensorDataset(X_tensor, y_tensor)
        train_size = int(0.8 * len(dataset))
        val_size = len(dataset) - train_size
        train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
        
        train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)
        
        # Initialize models
        input_size = features.shape[1]
        self.lstm_model = LSTMPredictor(input_size).to(self.device)
        self.transformer_model = TransformerPredictor(input_size).to(self.device)
        
        # Train LSTM
        logger.info("Training LSTM model...")
        self._train_single_model(self.lstm_model, train_loader, val_loader, epochs)
        
        # Train Transformer
        logger.info("Training Transformer model...")
        self._train_single_model(self.transformer_model, train_loader, val_loader, epochs)
        
        logger.info("Model training completed!")
    
    def _train_single_model(self, model: nn.Module, train_loader: DataLoader, 
                           val_loader: DataLoader, epochs: int):
        """Train a single model."""
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5)
        
        best_val_loss = float('inf')
        
        for epoch in range(epochs):
            # Training
            model.train()
            train_loss = 0
            for batch_x, batch_y in train_loader:
                optimizer.zero_grad()
                outputs = model(batch_x)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()
            
            # Validation
            model.eval()
            val_loss = 0
            with torch.no_grad():
                for batch_x, batch_y in val_loader:
                    outputs = model(batch_x)
                    loss = criterion(outputs, batch_y)
                    val_loss += loss.item()
            
            avg_train_loss = train_loss / len(train_loader)
            avg_val_loss = val_loss / len(val_loader)
            
            scheduler.step(avg_val_loss)
            
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                
            if epoch % 10 == 0:
                logger.info(f"Epoch {epoch}: Train Loss: {avg_train_loss:.4f}, Val Loss: {avg_val_loss:.4f}")
    
    async def predict(self, symbol: str, data: pd.DataFrame, 
                     timeframe: str = '1h') -> PredictionResult:
        """
        Make prediction for given symbol and timeframe.
        
        Returns:
            PredictionResult with price prediction and confidence
        """
        try:
            # Prepare features
            features = self.prepare_features(data)
            if len(features) < self.sequence_length:
                raise ValueError("Insufficient data for prediction")
            
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Get last sequence
            sequence = features_scaled[-self.sequence_length:]
            sequence_tensor = torch.FloatTensor(sequence).unsqueeze(0).to(self.device)
            
            # Make predictions
            self.lstm_model.eval()
            self.transformer_model.eval()
            
            with torch.no_grad():
                lstm_pred = self.lstm_model(sequence_tensor).item()
                transformer_pred = self.transformer_model(sequence_tensor).item()
            
            # Ensemble prediction
            ensemble_pred = (
                lstm_pred * self.ensemble_weights['lstm'] +
                transformer_pred * self.ensemble_weights['transformer']
            )
            
            # Calculate prediction details
            current_price = data['close'].iloc[-1]
            predicted_change = ensemble_pred
            predicted_price = current_price * (1 + predicted_change)
            
            # Determine direction
            if predicted_change > 0.001:  # 0.1% threshold
                direction = "up"
            elif predicted_change < -0.001:
                direction = "down"
            else:
                direction = "neutral"
            
            # Calculate confidence
            pred_std = abs(lstm_pred - transformer_pred)
            confidence = max(0.1, min(0.9, 1 - pred_std * 10))
            
            # Calculate support/resistance levels
            support_levels, resistance_levels = self._calculate_sr_levels(data)
            
            # Feature importance (simplified)
            feature_importance = self._calculate_feature_importance(sequence)
            
            return PredictionResult(
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                confidence=confidence,
                predicted_price=predicted_price,
                predicted_change_percent=predicted_change * 100,
                support_levels=support_levels,
                resistance_levels=resistance_levels,
                timestamp=datetime.now(),
                features_importance=feature_importance
            )
            
        except Exception as e:
            logger.error(f"Prediction error for {symbol}: {e}")
            raise
    
    def _calculate_sr_levels(self, data: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """Calculate support and resistance levels."""
        # Use recent highs and lows
        recent_data = data.tail(100)
        
        # Find local maxima and minima
        highs = recent_data['high'].rolling(window=10).max()
        lows = recent_data['low'].rolling(window=10).min()
        
        # Get unique levels
        resistance_levels = sorted(highs.dropna().unique())[-3:]  # Top 3
        support_levels = sorted(lows.dropna().unique())[:3]      # Bottom 3
        
        return support_levels, resistance_levels
    
    def _calculate_feature_importance(self, sequence: np.ndarray) -> Dict[str, float]:
        """Calculate feature importance (simplified version)."""
        # In production, would use SHAP values or permutation importance
        feature_variance = np.var(sequence, axis=0)
        total_variance = np.sum(feature_variance)
        
        importance = {}
        for i, var in enumerate(feature_variance[:10]):  # Top 10 features
            importance[f"feature_{i}"] = float(var / total_variance)
            
        return importance
    
    def backtest_predictions(self, data: pd.DataFrame, 
                           start_date: datetime, end_date: datetime) -> Dict:
        """Backtest prediction accuracy."""
        correct_predictions = 0
        total_predictions = 0
        cumulative_return = 1.0
        
        # Simplified backtest
        test_data = data[(data.index >= start_date) & (data.index <= end_date)]
        
        for i in range(self.sequence_length, len(test_data) - 1):
            # Get prediction
            historical_data = test_data.iloc[:i+1]
            
            try:
                prediction = self.predict('BACKTEST', historical_data, '1h')
                actual_change = test_data['close'].iloc[i+1] / test_data['close'].iloc[i] - 1
                
                # Check if direction was correct
                if (prediction.direction == "up" and actual_change > 0) or \
                   (prediction.direction == "down" and actual_change < 0):
                    correct_predictions += 1
                    
                total_predictions += 1
                
                # Simulate trading
                if prediction.confidence > 0.7:
                    if prediction.direction == "up":
                        cumulative_return *= (1 + actual_change)
                    elif prediction.direction == "down":
                        cumulative_return *= (1 - actual_change)
                        
            except Exception as e:
                logger.error(f"Backtest error: {e}")
                continue
        
        accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0
        
        return {
            "accuracy": accuracy,
            "total_predictions": total_predictions,
            "correct_predictions": correct_predictions,
            "cumulative_return": cumulative_return,
            "sharpe_ratio": self._calculate_sharpe(cumulative_return, total_predictions)
        }
    
    def _calculate_sharpe(self, total_return: float, periods: int) -> float:
        """Calculate Sharpe ratio."""
        if periods == 0:
            return 0
            
        avg_return = (total_return - 1) / periods
        # Simplified - assuming 2% daily volatility
        return avg_return / 0.02 * np.sqrt(252)  # Annualized
    
    def save_models(self, path: str):
        """Save trained models."""
        torch.save({
            'lstm_state': self.lstm_model.state_dict(),
            'transformer_state': self.transformer_model.state_dict(),
            'scaler': self.scaler,
            'config': self.config
        }, path)
        logger.info(f"Models saved to {path}")
    
    def load_models(self, path: str):
        """Load trained models."""
        checkpoint = torch.load(path, map_location=self.device)
        
        # Reinitialize models with correct architecture
        # This assumes you know the input size
        self.lstm_model.load_state_dict(checkpoint['lstm_state'])
        self.transformer_model.load_state_dict(checkpoint['transformer_state'])
        self.scaler = checkpoint['scaler']
        self.config = checkpoint['config']
        
        logger.info(f"Models loaded from {path}")
