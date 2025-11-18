"""
PRZYKŁAD implementacji dla giełdy z REST API.
NIE dla PrimeXBT - to tylko wzór!
"""

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
import requests


class ExampleExchangeClient:
    """Przykład implementacji dla typowej giełdy crypto."""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.example.com" if not testnet else "https://testnet.example.com"
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        })
    
    def _sign_request(self, method: str, path: str, data: Optional[Dict] = None) -> Dict[str, str]:
        """Podpisz request HMAC-SHA256 (typowe dla giełd)."""
        timestamp = str(int(time.time() * 1000))
        
        # Różne giełdy mają różne formaty podpisu
        if data:
            body = json.dumps(data, separators=(',', ':'))
        else:
            body = ""
            
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }
    
    def get_account_info(self) -> Dict[str, Any]:
        """Pobierz informacje o koncie."""
        path = "/api/v1/account"
        headers = self._sign_request("GET", path)
        
        response = self.session.get(
            f"{self.base_url}{path}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        order_type: str,  # "market" or "limit"
        quantity: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Złóż zlecenie."""
        path = "/api/v1/orders"
        
        data = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
            "timeInForce": "GTC"
        }
        
        if order_type.lower() == "limit" and price:
            data["price"] = str(price)
            
        if stop_loss:
            data["stopLoss"] = str(stop_loss)
            
        if take_profit:
            data["takeProfit"] = str(take_profit)
        
        headers = self._sign_request("POST", path, data)
        
        response = self.session.post(
            f"{self.base_url}{path}",
            json=data,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    def get_positions(self) -> Dict[str, Any]:
        """Pobierz otwarte pozycje."""
        path = "/api/v1/positions"
        headers = self._sign_request("GET", path)
        
        response = self.session.get(
            f"{self.base_url}{path}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()


# Przykład użycia z różnymi giełdami:

def binance_example():
    """Binance Futures API."""
    import ccxt  # biblioteka uniwersalna
    
    exchange = ccxt.binance({
        'apiKey': 'your-api-key',
        'secret': 'your-secret',
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'  # dla futures
        }
    })
    
    # Pobierz balance
    balance = exchange.fetch_balance()
    
    # Złóż zlecenie
    order = exchange.create_market_order(
        'BTC/USDT',
        'buy',
        0.001,
        params={
            'stopLoss': {'price': 58000},
            'takeProfit': {'price': 62000}
        }
    )
    
    return order


def bybit_example():
    """Bybit API."""
    from pybit.unified_trading import HTTP
    
    session = HTTP(
        testnet=False,
        api_key="your-api-key",
        api_secret="your-secret"
    )
    
    # Złóż zlecenie
    response = session.place_order(
        category="linear",
        symbol="BTCUSDT",
        side="Buy",
        orderType="Market",
        qty="0.001",
        stopLoss="58000",
        takeProfit="62000"
    )
    
    return response
