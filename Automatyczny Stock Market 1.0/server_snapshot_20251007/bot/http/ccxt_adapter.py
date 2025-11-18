"""
Adapter dla CCXT - uniwersalna biblioteka do 100+ giełd crypto.
Użyj tego zamiast PrimeXBT jeśli nie mają API.
"""

import ccxt
from typing import Dict, List, Optional, Any
import asyncio
import ccxt.async_support as ccxt_async
from pydantic import BaseModel

class Position(BaseModel):
    symbol: str
    side: str
    quantity: float
    entry_price: float
    unrealized_pnl: float
    leverage: float

class AccountInfo(BaseModel):
    free: float
    total: float
    used: float

class Order(BaseModel):
    id: str
    symbol: str
    side: str
    type: str
    amount: float
    price: Optional[float]
    status: str

class CCXTAdapter:
    """Universal asynchronous exchange adapter using CCXT library."""
    
    SUPPORTED_EXCHANGES = {
        'binance': ccxt_async.binance,
        'bybit': ccxt_async.bybit,
        'kraken': ccxt_async.kraken,
        'okx': ccxt_async.okx,
        'kucoin': ccxt_async.kucoin,
        'gateio': ccxt_async.gateio,
        'mexc': ccxt_async.mexc,
        'bitget': ccxt_async.bitget,
    }
    
    def __init__(
        self, 
        exchange_name: str,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        futures: bool = True
    ):
        if exchange_name not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"Exchange {exchange_name} not supported. Use: {list(self.SUPPORTED_EXCHANGES.keys())}")
            
        exchange_class = self.SUPPORTED_EXCHANGES[exchange_name]
        
        config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        }
        
        # Testnet config per exchange
        if testnet:
            if exchange_name == 'binance':
                config['options'] = {'defaultType': 'future'}
                config['urls'] = {
                    'api': {
                        'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
                        'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
                    }
                }
            elif exchange_name == 'bybit':
                config['options'] = {'testnet': True}
                
        self.exchange = exchange_class(config)
        self.futures = futures
        
    async def close(self):
        """Close the exchange connection."""
        await self.exchange.close()

    async def get_account_info(self) -> AccountInfo:
        """Get account balance and info."""
        try:
            balance = await self.exchange.fetch_balance()
            return AccountInfo(
                free=balance['free'].get('USDT', 0),
                total=balance['total'].get('USDT', 0),
                used=balance['used'].get('USDT', 0),
            )
        except ccxt.NetworkError as e:
            print(f"Network error fetching account info: {e}")
            raise
        except ccxt.ExchangeError as e:
            print(f"Exchange error fetching account info: {e}")
            raise

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get open positions."""
        try:
            positions_raw = await self.exchange.fetch_positions(symbols=[symbol] if symbol else None)
            
            return [
                Position(
                    symbol=pos['symbol'],
                    side=pos['side'],
                    quantity=pos['contracts'],
                    entry_price=pos.get('entryPrice') or pos.get('markPrice', 0),
                    unrealized_pnl=pos['unrealizedPnl'],
                    leverage=pos.get('leverage', 1)
                ) for pos in positions_raw if pos.get('contracts') and pos['contracts'] > 0
            ]
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error fetching positions: {e}")
            return []
    
    async def place_order(
        self,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        order_type: str,  # 'market' or 'limit'
        quantity: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        leverage: Optional[int] = None,
        reduce_only: bool = False,
    ) -> Order:
        """Place an order with optional SL/TP."""
        
        try:
            # Set leverage if specified
            if leverage and self.futures:
                await self.exchange.set_leverage(leverage, symbol)
            
            params = {'reduceOnly': reduce_only}
            if stop_loss:
                params['stopLoss'] = {'type': 'market', 'price': stop_loss}
            if take_profit:
                params['takeProfit'] = {'type': 'market', 'price': take_profit}

            if order_type.lower() == 'market':
                order_raw = await self.exchange.create_market_order(symbol, side, quantity, params)
            else:  # limit
                if not price:
                    raise ValueError("Price required for limit orders")
                order_raw = await self.exchange.create_limit_order(symbol, side, quantity, price, params)
            
            return Order(**order_raw)
            
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error placing order: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            return True
        except ccxt.OrderNotFound:
            print(f"Order {order_id} not found to cancel.")
            return False
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error canceling order: {e}")
            return False

    async def close_position(self, symbol: str) -> bool:
        """Close position for symbol."""
        try:
            positions = await self.get_positions(symbol)
            if not positions:
                return False
                
            for pos in positions:
                side = 'sell' if pos.side == 'long' else 'buy'
                await self.exchange.create_market_order(
                    symbol,
                    side,
                    pos.quantity,
                    {'reduceOnly': True}
                )
            return True
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error closing position: {e}")
            return False
    
    async def get_market_price(self, symbol: str) -> float:
        """Get current market price."""
        ticker = await self.exchange.fetch_ticker(symbol)
        return ticker['last']
    
    async def get_available_symbols(self) -> List[str]:
        """Get list of tradeable symbols."""
        markets = await self.exchange.load_markets()
        market_type = 'future' if self.futures else 'spot'
        return [
            symbol for symbol, market in markets.items()
            if market.get('active') and market.get('type') == market_type
        ]

# Przykład użycia:
async def main():
    # Użyj Binance testnet
    client = CCXTAdapter(
        exchange_name='binance',
        api_key='your_testnet_api_key',
        api_secret='your_testnet_api_secret',
        testnet=True,
        futures=True
    )
    
    try:
        # Sprawdź balans
        info = await client.get_account_info()
        print(f"Balance: {info.free}")
        
        # Złóż zlecenie
        order = await client.place_order(
            symbol='BTC/USDT',
            side='buy',
            order_type='market',
            quantity=0.001,
            stop_loss=58000,
            take_profit=62000,
            leverage=2
        )
        print(f"Order placed: {order.id}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
