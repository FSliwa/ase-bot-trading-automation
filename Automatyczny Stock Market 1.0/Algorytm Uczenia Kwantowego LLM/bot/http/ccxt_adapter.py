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

import time

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
            'options': {
                'adjustForTimeDifference': True,
            }
        }

        if exchange_name == 'kraken':
            config['nonce'] = lambda: int(time.time() * 1000000)
        
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

    async def get_specific_balance(self, currency: str) -> float:
        """Get balance for a specific currency."""
        try:
            balance = await self.exchange.fetch_balance()
            return balance['total'].get(currency, 0.0)
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error fetching {currency} balance: {e}")
            return 0.0

    async def get_all_balances(self) -> Dict[str, float]:
        """Get all non-zero balances."""
        try:
            balance = await self.exchange.fetch_balance()
            return {k: v for k, v in balance['total'].items() if v > 0}
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error fetching all balances: {e}")
            return {}

    async def convert_currency(self, from_currency: str, to_currency: str, amount: float) -> bool:
        """Convert currency using market order."""
        try:
            # Construct symbol, e.g., 'USDC/USDT' or 'EUR/USDC'
            # This is a simplification; real logic needs to check available pairs
            symbol = f"{from_currency}/{to_currency}"
            
            # Check if direct pair exists
            markets = await self.exchange.load_markets()
            if symbol in markets:
                # Sell from_currency to get to_currency
                await self.exchange.create_market_sell_order(symbol, amount)
                return True
            
            # Try reverse pair
            reverse_symbol = f"{to_currency}/{from_currency}"
            if reverse_symbol in markets:
                # Buy to_currency using from_currency
                # Note: amount here is in 'to_currency' for buy orders usually, 
                # but for market buy with cost (quote currency), it depends on exchange.
                # For simplicity/safety in this MVP, we might need to calculate price.
                # A safer bet for generic 'convert' is hard without specific exchange logic.
                # Assuming 'create_market_buy_order' takes amount in base currency (to_currency).
                # We have 'amount' in 'from_currency' (quote).
                
                ticker = await self.exchange.fetch_ticker(reverse_symbol)
                price = ticker['last']
                amount_to_buy = amount / price
                
                await self.exchange.create_market_buy_order(reverse_symbol, amount_to_buy)
                return True
                
            print(f"No direct pair found for {from_currency} -> {to_currency}")
            return False
            
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error converting currency: {e}")
            return False

    async def get_account_info(self) -> AccountInfo:
        """Get account balance and info (Legacy support, defaults to USDT)."""
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

    async def get_spot_balances(self) -> List[str]:
        """Get list of non-stablecoin assets with positive balance."""
        try:
            balance = await self.exchange.fetch_balance()
            # Filter for assets with total > 0
            # Exclude common stablecoins and fiat
            excluded_assets = {'USDT', 'USDC', 'USD', 'DAI', 'BUSD', 'EUR', 'PLN'}
            
            assets = [
                asset for asset, amount in balance['total'].items() 
                if amount > 0 and asset not in excluded_assets
            ]
            return assets
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error fetching spot balances: {e}")
            return []

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get open positions."""
        try:
            positions_raw = await self.exchange.fetch_positions(symbols=[symbol] if symbol else None)
            
            return [
                Position(
                    symbol=pos['symbol'],
                    side=pos['side'],
                    quantity=pos['contracts'],
                    entry_price=float(pos.get('entryPrice') or pos.get('markPrice') or 0.0),
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
                if self.exchange.id == 'kraken':
                    # Kraken uses 'leverage' in params
                    params = {'leverage': leverage}
                else:
                    try:
                        await self.exchange.set_leverage(leverage, symbol)
                    except Exception as e:
                        print(f"Warning: set_leverage failed: {e}")
            else:
                params = {}
            if stop_loss:
                params['stopLoss'] = {'type': 'market', 'price': stop_loss}
            if take_profit:
                params['takeProfit'] = {'type': 'market', 'price': take_profit}

            print(f"DEBUG: place_order params: {params}")
            if order_type.lower() == 'market':
                order_raw = await self.exchange.create_market_order(symbol, side, quantity, None, params)
            else:  # limit
                if not price:
                    raise ValueError("Price required for limit orders")
                order_raw = await self.exchange.create_limit_order(symbol, side, quantity, price, params)
            
            # Ensure status is a string
            if 'status' not in order_raw or order_raw['status'] is None:
                order_raw['status'] = 'open' # Default to open if missing
            
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

    async def get_top_volume_symbols(self, limit: int = 20) -> List[str]:
        """Get top volume USDT pairs."""
        try:
            print(f"DEBUG: Loading markets for {self.exchange.id}...")
            await self.exchange.load_markets()
            print("DEBUG: Fetching tickers...")
            tickers = await self.exchange.fetch_tickers()
            print(f"DEBUG: Fetched {len(tickers)} tickers")
            
            # Filter for USDT pairs
            usdt_tickers = []
            for symbol, ticker in tickers.items():
                if '/USDT' in symbol and ticker.get('quoteVolume'):
                    # Check if it's the right type (spot vs future) if possible
                    # For now, relying on symbol format and market loading
                    usdt_tickers.append((symbol, ticker['quoteVolume']))
            
            print(f"DEBUG: Found {len(usdt_tickers)} USDT tickers")
            
            # Sort by volume desc
            usdt_tickers.sort(key=lambda x: x[1], reverse=True)
            
            top_symbols = [t[0] for t in usdt_tickers[:limit]]
            print(f"DEBUG: Top symbols: {top_symbols}")
            return top_symbols
            
        except Exception as e:
            print(f"Error fetching top volume symbols: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_ticker_stats(self, symbol: str) -> Dict[str, float]:
        """Get 24h ticker statistics."""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return {
                'last': ticker['last'],
                'high': ticker['high'],
                'low': ticker['low'],
                'volume': ticker['quoteVolume'] if ticker.get('quoteVolume') else ticker['baseVolume'],
                'change_percent': ticker['percentage']
            }
        except Exception as e:
            print(f"Error fetching ticker stats for {symbol}: {e}")
            return {}

    async def get_order_book_depth(self, symbol: str, limit: int = 5) -> Dict[str, List[float]]:
        """Get top bids and asks."""
        try:
            order_book = await self.exchange.fetch_order_book(symbol, limit)
            return {
                'bids': order_book['bids'],
                'asks': order_book['asks']
            }
        except Exception as e:
            print(f"Error fetching order book for {symbol}: {e}")
            return {'bids': [], 'asks': []}

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[List[float]]:
        """Fetch historical OHLCV data."""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            print(f"Error fetching OHLCV for {symbol}: {e}")
            return []

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
