"""
Adapter dla CCXT - uniwersalna biblioteka do 100+ giełd crypto.
Użyj tego zamiast PrimeXBT jeśli nie mają API.
"""

import ccxt
import logging
from typing import Dict, List, Optional, Any
import asyncio
import ccxt.async_support as ccxt_async
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
RETRY_DELAY = 1.0  # seconds (base delay for exponential backoff)
REQUEST_TIMEOUT = 30000  # milliseconds
RATE_LIMIT_WAIT = 60  # seconds to wait when rate limited

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
        futures: bool = True,
        margin: bool = False
    ):
        self.margin = margin  # Store margin flag
        
        if exchange_name not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"Exchange {exchange_name} not supported. Use: {list(self.SUPPORTED_EXCHANGES.keys())}")
            
        exchange_class = self.SUPPORTED_EXCHANGES[exchange_name]
        
        config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'timeout': REQUEST_TIMEOUT,
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
        self._rate_limited_until = None  # Track rate limit cooldown
    
    async def _retry_async(self, func, *args, **kwargs):
        """
        Execute async function with retry logic for network errors and rate limiting.
        Uses exponential backoff for better resilience.
        """
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                # Check if we're in rate limit cooldown
                if self._rate_limited_until:
                    import time
                    now = time.time()
                    if now < self._rate_limited_until:
                        wait_time = self._rate_limited_until - now
                        logger.warning(f"Rate limited, waiting {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                    self._rate_limited_until = None
                
                return await func(*args, **kwargs)
                
            except ccxt.RateLimitExceeded as e:
                # Handle rate limiting with longer cooldown
                import time
                self._rate_limited_until = time.time() + RATE_LIMIT_WAIT
                logger.warning(f"Rate limit exceeded, cooling down for {RATE_LIMIT_WAIT}s: {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RATE_LIMIT_WAIT)
                    last_exception = e
                else:
                    raise
                    
            except ccxt.DDoSProtection as e:
                # DDoS protection triggered - back off significantly
                wait_time = RETRY_DELAY * (2 ** attempt) * 5  # Much longer backoff
                logger.warning(f"DDoS protection triggered (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait_time}s: {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    last_exception = e
                else:
                    raise
                
            except (ccxt.NetworkError, ccxt.RequestTimeout) as e:
                # Exponential backoff for network errors
                wait_time = RETRY_DELAY * (2 ** attempt)  # 1, 2, 4, 8, 16 seconds
                last_exception = e
                logger.warning(f"Network error (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {wait_time}s: {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    
            except ccxt.ExchangeNotAvailable as e:
                # Exchange down - wait longer
                wait_time = RETRY_DELAY * (2 ** attempt) * 2
                logger.warning(f"Exchange not available (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait_time}s: {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    last_exception = e
                else:
                    raise
                    
            except ccxt.ExchangeError as e:
                # Don't retry exchange errors (e.g., insufficient balance, invalid order)
                logger.error(f"Exchange error (not retrying): {e}")
                raise
                
            except Exception as e:
                # Unknown error - log and retry with backoff
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.error(f"Unexpected error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    last_exception = e
                else:
                    raise
        
        if last_exception:
            raise last_exception
        
    async def close(self):
        """Close the exchange connection."""
        await self.exchange.close()

    async def get_specific_balance(self, currency: str) -> float:
        """Get balance for a specific currency.
        
        FIX 2025-12-14: For Binance, also check margin account if spot balance is 0.
        """
        try:
            balance = await self._retry_async(self.exchange.fetch_balance)
            spot_balance = balance['total'].get(currency, 0.0)
            
            # FIX: If spot balance is 0 and this is Binance, try margin account
            if spot_balance < 1.0 and self.exchange.id == 'binance':
                try:
                    # Fetch cross margin balance
                    margin_balance = await self._retry_async(
                        self.exchange.fetch_balance, 
                        {'type': 'margin'}
                    )
                    margin_amount = margin_balance['total'].get(currency, 0.0)
                    if margin_amount > spot_balance:
                        logger.info(f"📊 Binance: Using margin balance for {currency}: {margin_amount:.2f} (spot was {spot_balance:.2f})")
                        return margin_amount
                except Exception as margin_err:
                    logger.debug(f"Could not fetch margin balance: {margin_err}")
            
            return spot_balance
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error fetching {currency} balance: {e}")
            return 0.0

    async def get_all_balances(self) -> Dict[str, float]:
        """Get all non-zero balances.
        
        FIX 2025-12-14: For Binance, merge spot and margin balances.
        """
        try:
            balance = await self._retry_async(self.exchange.fetch_balance)
            result = {k: v for k, v in balance['total'].items() if v > 0}
            
            # FIX: For Binance, also include margin balances
            if self.exchange.id == 'binance':
                try:
                    margin_balance = await self._retry_async(
                        self.exchange.fetch_balance,
                        {'type': 'margin'}
                    )
                    for k, v in margin_balance['total'].items():
                        if v > 0:
                            # Merge: use max of spot and margin
                            result[k] = max(result.get(k, 0), v)
                except Exception as margin_err:
                    logger.debug(f"Could not fetch margin balances: {margin_err}")
            
            return result
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error fetching all balances: {e}")
            return {}

    async def get_margin_info(self) -> Dict[str, Any]:
        """
        Get margin/leverage trading information.
        P1 FIX: Added for proper margin level checking.
        P0 FIX 2025-12-13: Use spot balance as fallback when margin fields are 0.
        
        Returns:
            Dict with 'free_margin', 'used_margin', 'margin_level', 'can_trade'
        """
        try:
            balance = await self._retry_async(self.exchange.fetch_balance)
            
            if self.exchange.id == 'kraken':
                # Kraken provides margin info in balance response
                info = balance.get('info', {})
                result = info.get('result', {})
                
                # Kraken margin fields
                trade_balance = float(result.get('tb', 0) or 0)  # Trade balance
                margin_level = float(result.get('ml', 0) or 0)   # Margin level %
                free_margin = float(result.get('mf', 0) or 0)    # Free margin
                used_margin = float(result.get('m', 0) or 0)     # Used margin
                equity = float(result.get('e', 0) or 0)          # Equity
                
                # P0 FIX: If margin fields are 0, use spot balance as available margin
                # This happens when user has no margin positions or Kraken returns stale data
                if free_margin <= 0 and trade_balance <= 0:
                    # Fallback to spot balances (USDC/USDT/USD)
                    free_balances = balance.get('free', {})
                    spot_margin = (
                        float(free_balances.get('USDC', 0) or 0) +
                        float(free_balances.get('USDT', 0) or 0) +
                        float(free_balances.get('USD', 0) or 0) +
                        float(free_balances.get('ZUSD', 0) or 0)  # Kraken uses ZUSD internally
                    )
                    if spot_margin > 0:
                        free_margin = spot_margin
                        logger.info(f"📊 Kraken: Using spot balance as margin proxy: ${spot_margin:.2f}")
                
                # Calculate available margin more accurately
                # Available = equity - used_margin (or trade_balance if no positions)
                calculated_free = equity - used_margin if equity > 0 else trade_balance
                
                # Use the best available value
                effective_free_margin = max(free_margin, calculated_free, trade_balance)
                
                # Kraken requires margin level > 100% to open new positions
                # Safe trading usually requires > 150%
                # If margin_level is 0 and we have balance, we're not leveraged yet
                can_trade = (margin_level == 0 and effective_free_margin > 10) or margin_level > 150
                
                margin_info = {
                    'free_margin': effective_free_margin,
                    'used_margin': used_margin,
                    'margin_level': margin_level,
                    'trade_balance': trade_balance,
                    'equity': equity,
                    'can_trade': can_trade,
                    'exchange': 'kraken',
                    'min_margin_level': 150,  # Safe minimum
                }
                
                logger.info(
                    f"📊 Kraken Margin: Free=${effective_free_margin:.2f} | Used=${used_margin:.2f} | "
                    f"Equity=${equity:.2f} | Level={margin_level:.0f}% | Can Trade: {'✅' if can_trade else '❌'}"
                )
                return margin_info
            
            # Generic fallback for other exchanges
            free = balance.get('free', {})
            used = balance.get('used', {})
            
            # Sum up USDT/USDC as margin proxy
            free_margin = float(free.get('USDT', 0) or 0) + float(free.get('USDC', 0) or 0)
            used_margin = float(used.get('USDT', 0) or 0) + float(used.get('USDC', 0) or 0)
            
            return {
                'free_margin': free_margin,
                'used_margin': used_margin,
                'margin_level': 0,  # Unknown for generic
                'can_trade': free_margin > 10,  # At least $10 to trade
                'exchange': self.exchange.id,
            }
            
        except Exception as e:
            logger.warning(f"Could not get margin info: {e}")
            return {
                'free_margin': 0,
                'used_margin': 0,
                'margin_level': 0,
                'can_trade': False,
                'error': str(e),
            }

    async def check_can_open_position(self, symbol: str, quantity: float, current_price: float, leverage: int = 1) -> Dict[str, Any]:
        """
        Check if we can open a new position with the given parameters.
        
        Returns:
            Dict with 'can_open', 'reason', 'available_margin', 'required_margin'
        """
        try:
            order_value = quantity * current_price
            required_margin = order_value / leverage
            
            margin_info = await self.get_margin_info()
            free_margin = margin_info.get('free_margin', 0)
            can_trade = margin_info.get('can_trade', False)
            margin_level = margin_info.get('margin_level', 0)
            
            # Check if enough free margin
            if not can_trade:
                return {
                    'can_open': False,
                    'reason': f"Margin level too low ({margin_level:.0f}%, need >150%)",
                    'available_margin': free_margin,
                    'required_margin': required_margin,
                    'suggestion': 'Close some positions or add funds to increase margin level',
                }
            
            if free_margin < required_margin:
                return {
                    'can_open': False,
                    'reason': f"Insufficient free margin (${free_margin:.2f} < ${required_margin:.2f})",
                    'available_margin': free_margin,
                    'required_margin': required_margin,
                    'suggestion': f"Reduce position size to max ${free_margin * leverage:.2f}",
                }
            
            return {
                'can_open': True,
                'reason': 'Sufficient margin available',
                'available_margin': free_margin,
                'required_margin': required_margin,
                'margin_utilization': (required_margin / free_margin * 100) if free_margin > 0 else 0,
            }
            
        except Exception as e:
            logger.warning(f"Could not check margin requirements: {e}")
            return {
                'can_open': True,  # Allow to try (exchange will reject if invalid)
                'reason': f"Could not verify margin: {e}",
                'available_margin': 0,
                'required_margin': 0,
            }

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
                
            logger.warning(f"No direct pair found for {from_currency} -> {to_currency}")
            return False
            
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error converting currency: {e}")
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
            logger.error(f"Network error fetching account info: {e}")
            raise
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error fetching account info: {e}")
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
            logger.error(f"Error fetching spot balances: {e}")
            return []

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get open positions. For margin mode, returns borrowed positions from balance."""
        try:
            # Margin mode: Get positions from borrowed balances
            if self.margin:
                return await self._get_margin_positions()
            
            # Kraken/Spot mode: Get positions from spot balances with entry price from trades
            if self.exchange.id == 'kraken':
                return await self._get_spot_positions_with_entry_price()
            
            # Binance SPOT mode (not futures): Use spot balances like Kraken
            if self.exchange.id == 'binance' and not self.futures:
                return await self._get_spot_positions_with_entry_price()
            
            # Futures mode: Use fetch_positions
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
            logger.error(f"Error fetching positions: {e}")
            return []
    
    async def _get_spot_positions_with_entry_price(self) -> List[Position]:
        """
        Get spot positions from balance with calculated entry price from trade history.
        Used for Kraken and other spot exchanges.
        """
        try:
            balance = await self.exchange.fetch_balance()
            positions = []
            
            # Exclude stablecoins and fiat
            excluded_assets = {'USDT', 'USDC', 'USD', 'DAI', 'BUSD', 'EUR', 'PLN', 'GBP', 'CHF'}
            
            for asset, data in balance.items():
                if isinstance(data, dict):
                    total = float(data.get('total', 0) or 0)
                    
                    # If asset has positive balance (not stablecoins), it's a LONG position
                    if total > 0 and asset not in excluded_assets:
                        # Try to get entry price from recent trades
                        entry_price = await self._calculate_entry_price_from_trades(asset, total)
                        
                        # Determine quote currency (USDC for Kraken, USDT for Binance)
                        quote = 'USDC' if self.exchange.id == 'kraken' else 'USDT'
                        symbol = f"{asset}/{quote}"
                        
                        # Get current price for unrealized P&L
                        try:
                            ticker = await self.exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            unrealized_pnl = (current_price - entry_price) * total if entry_price > 0 else 0.0
                        except:
                            current_price = entry_price
                            unrealized_pnl = 0.0
                        
                        positions.append(Position(
                            symbol=symbol,
                            side='long',
                            quantity=total,
                            entry_price=entry_price,
                            unrealized_pnl=unrealized_pnl,
                            leverage=1
                        ))
                        
                        logger.info(f"📊 Found spot position: {symbol} | Qty: {total:.6f} | Entry: {entry_price:.4f}")
            
            return positions
        except Exception as e:
            logger.error(f"Error fetching spot positions: {e}")
            return []
    
    async def _calculate_entry_price_from_trades(self, asset: str, current_qty: float) -> float:
        """
        Calculate weighted average entry price from recent buy trades.
        Uses FIFO method to approximate entry price for current holdings.
        """
        try:
            # Try different quote currencies
            quotes = ['USDC', 'USDT', 'USD']
            trades = []
            
            for quote in quotes:
                symbol = f"{asset}/{quote}"
                try:
                    trades = await self.exchange.fetch_my_trades(symbol, limit=50)
                    if trades:
                        break
                except:
                    continue
            
            if not trades:
                logger.warning(f"No trades found for {asset}, using current market price as entry")
                # Fallback: use current price
                for quote in quotes:
                    try:
                        ticker = await self.exchange.fetch_ticker(f"{asset}/{quote}")
                        return ticker['last']
                    except:
                        continue
                return 0.0
            
            # Calculate weighted average from recent buys
            total_cost = 0.0
            total_qty = 0.0
            remaining_qty = current_qty
            
            # Sort by datetime descending (newest first - LIFO for calculation)
            sorted_trades = sorted(trades, key=lambda t: t['datetime'], reverse=True)
            
            for trade in sorted_trades:
                if trade['side'] == 'buy' and remaining_qty > 0:
                    trade_qty = min(trade['amount'], remaining_qty)
                    total_cost += trade_qty * trade['price']
                    total_qty += trade_qty
                    remaining_qty -= trade_qty
            
            if total_qty > 0:
                avg_price = total_cost / total_qty
                logger.debug(f"Calculated entry price for {asset}: {avg_price:.4f} from {len(trades)} trades")
                return avg_price
            
            return 0.0
            
        except Exception as e:
            logger.warning(f"Could not calculate entry price for {asset}: {e}")
            return 0.0
    
    async def _get_margin_positions(self) -> List[Position]:
        """Get margin positions from borrowed balances (for Binance Margin)."""
        try:
            balance = await self.exchange.fetch_balance({'type': 'margin'})
            positions = []
            
            for asset, data in balance.items():
                if isinstance(data, dict):
                    borrowed = float(data.get('borrowed', 0) or 0)
                    free = float(data.get('free', 0) or 0)
                    
                    # If asset is borrowed, it's a SHORT position
                    if borrowed > 0:
                        symbol = f"{asset}/USDT"
                        positions.append(Position(
                            symbol=symbol,
                            side='short',
                            quantity=borrowed,
                            entry_price=0.0,
                            unrealized_pnl=0.0,
                            leverage=1
                        ))
                    # If asset has positive free balance (not stablecoins), it's a LONG position
                    elif free > 0 and asset not in ['USDT', 'USDC', 'USD', 'BUSD']:
                        symbol = f"{asset}/USDT"
                        positions.append(Position(
                            symbol=symbol,
                            side='long',
                            quantity=free,
                            entry_price=0.0,
                            unrealized_pnl=0.0,
                            leverage=1
                        ))
            
            return positions
        except Exception as e:
            logger.error(f"Error fetching margin positions: {e}")
            return []
    
    async def get_min_order_amount(self, symbol: str, current_price: Optional[float] = None) -> Dict[str, float]:
        """
        Get minimum order requirements for a symbol.
        
        Returns:
            Dict with 'min_amount' (in base currency), 'min_cost' (in quote currency, e.g. USD)
        """
        try:
            await self.exchange.load_markets()
            market = self.exchange.markets.get(symbol)
            
            if not market:
                logger.warning(f"Market {symbol} not found, using defaults")
                return {'min_amount': 0.0001, 'min_cost': 10.0}
            
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            cost_limits = limits.get('cost', {})
            
            min_amount = amount_limits.get('min', 0.0001)
            min_cost = cost_limits.get('min', 5.0)  # Most exchanges have ~$5-10 minimum
            
            # Exchange-specific minimums (fallback values)
            if self.exchange.id == 'kraken':
                # Kraken typically requires $5-10 minimum depending on pair
                if min_cost is None or min_cost < 5.0:
                    min_cost = 5.0
            elif self.exchange.id == 'binance':
                # Binance minimum is usually $10-15 for spot
                if min_cost is None or min_cost < 10.0:
                    min_cost = 10.0
            
            return {
                'min_amount': float(min_amount) if min_amount else 0.0001,
                'min_cost': float(min_cost) if min_cost else 10.0
            }
        except Exception as e:
            logger.warning(f"Could not get min order for {symbol}: {e}")
            return {'min_amount': 0.0001, 'min_cost': 10.0}
    
    async def adjust_quantity_to_minimum(self, symbol: str, quantity: float, current_price: float) -> float:
        """
        Adjust quantity to meet exchange minimum requirements.
        
        Returns adjusted quantity (increased if below minimum).
        """
        minimums = await self.get_min_order_amount(symbol, current_price)
        min_amount = minimums['min_amount']
        min_cost = minimums['min_cost']
        
        # Calculate order value
        order_value = quantity * current_price
        
        # If below minimum cost, increase quantity
        if order_value < min_cost:
            new_quantity = (min_cost * 1.1) / current_price  # Add 10% buffer
            logger.info(
                f"📊 Adjusting {symbol} quantity: {quantity:.6f} → {new_quantity:.6f} "
                f"(${order_value:.2f} → ${new_quantity * current_price:.2f}) to meet minimum ${min_cost}"
            )
            return new_quantity
        
        # If below minimum amount, use minimum amount
        if quantity < min_amount:
            logger.info(
                f"📊 Adjusting {symbol} quantity: {quantity:.6f} → {min_amount:.6f} "
                f"to meet minimum amount"
            )
            return min_amount
        
        return quantity

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
        """Place an order with optional SL/TP and auto-adjusted leverage."""
        
        logger.debug(f"place_order ENTRY: {symbol} {side} qty={quantity} price={price}")
        
        try:
            params = {}
            actual_leverage = 1
            
            # ===== NEW: Get current price and adjust quantity to meet minimums =====
            current_price = price
            if not current_price:
                try:
                    ticker = await self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                except:
                    current_price = 0
            
            if current_price and current_price > 0:
                original_qty = quantity
                quantity = await self.adjust_quantity_to_minimum(symbol, quantity, current_price)
                if quantity != original_qty:
                    logger.info(f"📊 Order quantity adjusted: {original_qty:.6f} → {quantity:.6f} to meet exchange minimum")
            
            # ========================================================================
            # L3 FIX: Proper leverage handling for SPOT vs FUTURES/MARGIN
            # ========================================================================
            # SPOT trading NEVER has leverage (always 1x)
            # Only FUTURES/MARGIN can use leverage
            # ========================================================================
            
            is_spot_mode = not self.futures and not self.margin
            
            if is_spot_mode:
                # SPOT MODE: Force leverage to 1 - no leverage supported
                if leverage and leverage > 1:
                    logger.warning(
                        f"⚠️ L3 FIX: Leverage {leverage}x requested but trading in SPOT mode. "
                        f"SPOT does not support leverage. Using 1x (no leverage)."
                    )
                actual_leverage = 1
            elif leverage:
                # FUTURES/MARGIN MODE: Apply leverage
                if self.exchange.id == 'kraken':
                    # Kraken: get best available leverage and pass in params
                    actual_leverage = await self.get_best_leverage(symbol, leverage)
                    params['leverage'] = actual_leverage
                elif self.exchange.id == 'binance':
                    # Binance FUTURES: Set leverage via API
                    actual_leverage = await self.set_leverage_safe(symbol, leverage)
                else:
                    # Other exchanges: try to set leverage with fallback
                    actual_leverage = await self.set_leverage_safe(symbol, leverage)
                    
                logger.info(f"📊 {symbol}: Using {actual_leverage}x leverage (requested: {leverage}x)")
            else:
                actual_leverage = 1
            
            # Exchange-specific SL/TP params
            if stop_loss or take_profit:
                if self.exchange.id == 'binance':
                    # Binance SPOT: SL/TP not supported in single order - skip params
                    # Binance FUTURES: Use unified stopLoss/takeProfit
                    if self.futures:
                        if stop_loss:
                            params['stopLoss'] = {'type': 'market', 'triggerPrice': stop_loss}
                        if take_profit:
                            params['takeProfit'] = {'type': 'market', 'triggerPrice': take_profit}
                    else:
                        # SPOT mode: Log that SL/TP will be managed by Position Monitor
                        logger.info(f"📊 Binance Spot: SL/TP not in order params, will be managed by Position Monitor (SL={stop_loss}, TP={take_profit})")
                elif self.exchange.id == 'bybit':
                    # Bybit: Use stopLoss/takeProfit with price
                    if stop_loss:
                        params['stopLoss'] = {'type': 'market', 'triggerPrice': stop_loss}
                    if take_profit:
                        params['takeProfit'] = {'type': 'market', 'triggerPrice': take_profit}
                elif self.exchange.id == 'okx':
                    # OKX: Use slTriggerPx/tpTriggerPx
                    if stop_loss:
                        params['slTriggerPx'] = str(stop_loss)
                        params['slOrdPx'] = '-1'  # Market price
                    if take_profit:
                        params['tpTriggerPx'] = str(take_profit)
                        params['tpOrdPx'] = '-1'  # Market price
                elif self.exchange.id == 'bitget':
                    # Bitget: Use presetStopLossPrice/presetTakeProfitPrice
                    if stop_loss:
                        params['presetStopLossPrice'] = str(stop_loss)
                    if take_profit:
                        params['presetTakeProfitPrice'] = str(take_profit)
                else:
                    # Generic CCXT unified format
                    if stop_loss:
                        params['stopLoss'] = {'type': 'market', 'price': stop_loss}
                    if take_profit:
                        params['takeProfit'] = {'type': 'market', 'price': take_profit}

            # NEW v2.5: Final cleanup for Binance SPOT - remove unsupported parameters
            # MUST be AFTER all params are set
            if self.exchange.id == 'binance' and not self.futures:
                # Binance SPOT doesn't support: leverage, reduceOnly, stopLoss, takeProfit
                params.pop('leverage', None)
                params.pop('reduceOnly', None)
                params.pop('stopLoss', None)
                params.pop('takeProfit', None)
                logger.info(f"📊 Binance SPOT: Final params after cleanup: {params}")

            logger.debug(f"place_order for {self.exchange.id} params: {params}")
            if order_type.lower() == 'market':
                order_raw = await self.exchange.create_market_order(symbol, side, quantity, None, params)
            else:  # limit
                if not price:
                    raise ValueError("Price required for limit orders")
                order_raw = await self.exchange.create_limit_order(symbol, side, quantity, price, params)
            
            # Log SL/TP info
            if stop_loss or take_profit:
                logger.debug(f"Order placed with SL={stop_loss}, TP={take_profit}")
            
            # Ensure status is a string
            if 'status' not in order_raw or order_raw['status'] is None:
                order_raw['status'] = 'open' # Default to open if missing
            
            return Order(**order_raw)
            
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error placing order: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            return True
        except ccxt.OrderNotFound:
            logger.warning(f"Order {order_id} not found to cancel.")
            return False
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error canceling order: {e}")
            return False

    async def close_position(self, symbol: str) -> bool:
        """
        Close position for symbol.
        
        Handles different exchange modes:
        - Futures: Uses reduceOnly=True to close without opening opposite position
        - SPOT: Simple market sell (no reduceOnly support)
        - Margin: Uses reduceOnly if available
        """
        try:
            positions = await self.get_positions(symbol)
            if not positions:
                logger.info(f"No position found for {symbol} to close")
                return False
                
            for pos in positions:
                side = 'sell' if pos.side == 'long' else 'buy'
                
                # Build params based on exchange mode
                params = {}
                
                # Binance SPOT doesn't support reduceOnly
                if self.exchange.id == 'binance' and not self.futures:
                    # SPOT mode: Just sell the asset, no special params
                    logger.info(f"📊 Closing SPOT position: {symbol} | SELL {pos.quantity}")
                elif self.exchange.id == 'kraken':
                    # Kraken doesn't support reduceOnly even in margin mode via spot API
                    logger.info(f"📊 Closing Kraken position: {symbol} | {side.upper()} {pos.quantity} (no reduceOnly)")
                elif self.futures or self.margin:
                    # Futures/Margin mode: Use reduceOnly
                    params['reduceOnly'] = True
                    logger.info(f"📊 Closing Futures/Margin position: {symbol} | {side.upper()} {pos.quantity}")
                
                await self.exchange.create_market_order(
                    symbol,
                    side,
                    pos.quantity,
                    params if params else None
                )
                
            return True
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            return False
    
    async def get_market_price(self, symbol: str) -> float:
        """Get current market price."""
        ticker = await self.exchange.fetch_ticker(symbol)
        return ticker['last']
    
    async def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get full ticker data for a symbol.
        
        Returns:
            Dict with keys: last, bid, ask, high, low, volume, quoteVolume, etc.
            Returns None if symbol not found or error.
        """
        try:
            ticker = await self._retry_async(self.exchange.fetch_ticker, symbol)
            return {
                'symbol': symbol,
                'last': ticker.get('last'),
                'bid': ticker.get('bid'),
                'ask': ticker.get('ask'),
                'high': ticker.get('high'),
                'low': ticker.get('low'),
                'volume': ticker.get('baseVolume'),
                'quoteVolume': ticker.get('quoteVolume'),
                'change': ticker.get('change'),
                'percentage': ticker.get('percentage'),
                'timestamp': ticker.get('timestamp'),
            }
        except Exception as e:
            logger.warning(f"Could not fetch ticker for {symbol}: {e}")
            return None
    
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
            logger.debug(f"Loading markets for {self.exchange.id}...")
            await self.exchange.load_markets()
            logger.debug("Fetching tickers...")
            tickers = await self.exchange.fetch_tickers()
            logger.debug(f"Fetched {len(tickers)} tickers")
            
            # Filter for USDT pairs
            usdt_tickers = []
            for symbol, ticker in tickers.items():
                if '/USDT' in symbol and ticker.get('quoteVolume'):
                    # Check if it's the right type (spot vs future) if possible
                    # For now, relying on symbol format and market loading
                    usdt_tickers.append((symbol, ticker['quoteVolume']))
            
            logger.debug(f"Found {len(usdt_tickers)} USDT tickers")
            
            # Sort by volume desc
            usdt_tickers.sort(key=lambda x: x[1], reverse=True)
            
            top_symbols = [t[0] for t in usdt_tickers[:limit]]
            logger.debug(f"Top symbols: {top_symbols}")
            return top_symbols
            
        except Exception as e:
            logger.error(f"Error fetching top volume symbols: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_max_leverage(self, symbol: str) -> int:
        """
        Get maximum available leverage for a symbol.
        Returns the max leverage the exchange supports for this pair.
        """
        try:
            await self.exchange.load_markets()
            
            if symbol not in self.exchange.markets:
                logger.warning(f"Symbol {symbol} not found in markets")
                return 1
            
            market = self.exchange.markets[symbol]
            
            # Different exchanges store leverage info differently
            max_leverage = 1
            
            # Check market limits
            if 'limits' in market and 'leverage' in market.get('limits', {}):
                leverage_limits = market['limits']['leverage']
                if leverage_limits and 'max' in leverage_limits:
                    max_leverage = int(leverage_limits['max'] or 1)
            
            # Check market info for leverage
            if max_leverage == 1 and 'info' in market:
                info = market['info']
                # Binance
                if 'maxLeverage' in info:
                    max_leverage = int(info['maxLeverage'])
                # Bybit
                elif 'leverageFilter' in info:
                    max_leverage = int(info['leverageFilter'].get('maxLeverage', 1))
                # OKX
                elif 'lever' in info:
                    max_leverage = int(info['lever'])
                # Kraken - typically lower leverage (2-5x for crypto)
                elif self.exchange.id == 'kraken':
                    # Kraken has limited leverage, usually 2-5x for crypto
                    max_leverage = 5  # Conservative default for Kraken
            
            # Fallback for exchanges without leverage info
            if max_leverage <= 1 and self.futures:
                # Try to fetch leverage brackets if available (Binance, etc.)
                try:
                    if hasattr(self.exchange, 'fetch_leverage_tiers'):
                        tiers = await self.exchange.fetch_leverage_tiers([symbol])
                        if symbol in tiers and tiers[symbol]:
                            max_leverage = max(t.get('maxLeverage', 1) for t in tiers[symbol])
                except Exception as e:
                    logger.debug(f"Could not fetch leverage tiers: {e}")
            
            return max(1, max_leverage)
            
        except Exception as e:
            logger.error(f"Error getting max leverage for {symbol}: {e}")
            return 1

    async def get_best_leverage(self, symbol: str, desired_leverage: int = 10) -> int:
        """
        Get the best available leverage for a symbol.
        Tries to use desired_leverage, but falls back to lower values if not available.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            desired_leverage: Preferred leverage (default 10x)
            
        Returns:
            The highest available leverage up to desired_leverage
        """
        try:
            max_leverage = await self.get_max_leverage(symbol)
            
            # Return the minimum of desired and max available
            best_leverage = min(desired_leverage, max_leverage)
            
            if best_leverage < desired_leverage:
                logger.info(
                    f"⚠️ {symbol}: Requested {desired_leverage}x leverage not available. "
                    f"Using {best_leverage}x (max available: {max_leverage}x)"
                )
            else:
                logger.info(f"✅ {symbol}: Using {best_leverage}x leverage")
            
            return max(1, best_leverage)
            
        except Exception as e:
            logger.error(f"Error determining best leverage for {symbol}: {e}")
            return 1

    async def set_leverage_safe(self, symbol: str, desired_leverage: int = 10) -> int:
        """
        Safely set leverage for a symbol, falling back to lower values if needed.
        
        Args:
            symbol: Trading pair
            desired_leverage: Preferred leverage (default 10x)
            
        Returns:
            The actual leverage that was set
        """
        if not self.futures:
            return 1
        
        leverage_to_try = [desired_leverage, 5, 3, 2, 1]
        
        for leverage in leverage_to_try:
            if leverage > desired_leverage:
                continue
                
            try:
                if self.exchange.id == 'kraken':
                    # Kraken doesn't have a separate set_leverage endpoint
                    # Leverage is set per-order in params
                    max_lev = await self.get_max_leverage(symbol)
                    actual_leverage = min(leverage, max_lev)
                    logger.info(f"Kraken: Will use {actual_leverage}x leverage for {symbol}")
                    return actual_leverage
                else:
                    await self.exchange.set_leverage(leverage, symbol)
                    logger.info(f"✅ Set {leverage}x leverage for {symbol}")
                    return leverage
                    
            except ccxt.ExchangeError as e:
                error_msg = str(e).lower()
                # Check if it's a leverage-related error
                if 'leverage' in error_msg or 'margin' in error_msg:
                    logger.warning(f"Cannot set {leverage}x for {symbol}: {e}")
                    continue
                else:
                    # Different type of error, might be symbol-specific
                    logger.error(f"Exchange error setting leverage: {e}")
                    break
            except Exception as e:
                logger.error(f"Unexpected error setting leverage: {e}")
                break
        
        logger.warning(f"Could not set any leverage for {symbol}, defaulting to 1x")
        return 1

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
            logger.error(f"Error fetching ticker stats for {symbol}: {e}")
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
            logger.error(f"Error fetching order book for {symbol}: {e}")
            return {'bids': [], 'asks': []}

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[List[float]]:
        """Fetch historical OHLCV data."""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return []

    # ========================================================================
    # L1 FIX: OCO Orders for Binance SPOT - Hardware SL/TP protection
    # ========================================================================
    
    async def place_order_with_oco(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        order_type: str = 'market',
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Place order with OCO (One-Cancels-Other) for hardware SL/TP protection.
        
        L1 FIX: For Binance SPOT, after placing main order, this creates an OCO
        order that will:
        - Set a limit sell at take_profit
        - Set a stop-loss limit at stop_loss
        
        If either triggers, the other is automatically cancelled.
        
        Returns:
            Dict with main_order, oco_order (if created), success status
        """
        result = {
            'success': False,
            'main_order': None,
            'oco_order': None,
            'error': None,
            'oco_supported': False,
        }
        
        try:
            # First place the main order
            main_order = await self.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                # Don't pass SL/TP to main order - we'll use OCO
            )
            result['main_order'] = main_order
            
            # For SELL orders (closing longs) or if no SL/TP specified - just return main order
            if side.lower() == 'sell' or (not stop_loss and not take_profit):
                result['success'] = True
                return result
            
            # Check if exchange supports OCO
            if self.exchange.id == 'binance' and not self.futures:
                result['oco_supported'] = True
                
                # Wait a moment for order to fill
                await asyncio.sleep(0.5)
                
                # Get filled quantity and price
                filled_qty = getattr(main_order, 'filled', quantity) or quantity
                executed_price = getattr(main_order, 'average', None)
                
                if not executed_price:
                    ticker = await self.exchange.fetch_ticker(symbol)
                    executed_price = ticker['last']
                
                if filled_qty > 0 and stop_loss and take_profit:
                    try:
                        # Calculate stop limit price (slightly below stop price for sells)
                        stop_limit_price = stop_loss * 0.995  # 0.5% below stop
                        
                        # Create OCO order using CCXT
                        # For Binance, we need to use create_order with special params
                        oco_params = {
                            'stopPrice': stop_loss,  # Trigger price for stop-loss
                            'stopLimitPrice': stop_limit_price,
                            'stopLimitTimeInForce': 'GTC',
                        }
                        
                        # Try using Binance-specific OCO endpoint
                        if hasattr(self.exchange, 'create_oco_order'):
                            oco_order = await self.exchange.create_oco_order(
                                symbol=symbol,
                                side='sell',  # Always sell for long position exit
                                quantity=filled_qty,
                                price=take_profit,  # Limit price (TP)
                                stopPrice=stop_loss,  # Stop trigger price
                                stopLimitPrice=stop_limit_price,  # Stop limit price
                            )
                        else:
                            # Fallback: Create separate stop-loss order
                            # Binance SPOT: Use STOP_LOSS_LIMIT order type
                            oco_order = await self.exchange.create_order(
                                symbol=symbol,
                                type='STOP_LOSS_LIMIT',
                                side='sell',
                                amount=filled_qty,
                                price=stop_limit_price,
                                params={
                                    'stopPrice': stop_loss,
                                    'timeInForce': 'GTC',
                                }
                            )
                            
                            # Also create the limit order for TP (not OCO but gives protection)
                            if take_profit:
                                await self.exchange.create_order(
                                    symbol=symbol,
                                    type='LIMIT',
                                    side='sell',
                                    amount=filled_qty,
                                    price=take_profit,
                                    params={'timeInForce': 'GTC'}
                                )
                        
                        result['oco_order'] = oco_order
                        result['success'] = True
                        
                        logger.info(
                            f"✅ L1 FIX: OCO order placed for {symbol} | "
                            f"SL: ${stop_loss:.2f} | TP: ${take_profit:.2f} | "
                            f"Qty: {filled_qty:.6f} - Position is now hardware-protected!"
                        )
                        
                    except ccxt.NotSupported as e:
                        logger.warning(f"⚠️ OCO not supported by exchange: {e}")
                        result['error'] = f"OCO not supported: {e}"
                        result['success'] = True  # Main order succeeded
                        
                    except Exception as e:
                        logger.error(f"⚠️ Failed to create OCO order: {e}")
                        result['error'] = f"OCO creation failed: {e}"
                        result['success'] = True  # Main order succeeded
                else:
                    result['success'] = True
                    if filled_qty == 0:
                        result['error'] = "Main order not filled, skipping OCO"
            else:
                # Non-Binance or Futures - OCO handled differently
                result['success'] = True
                result['oco_supported'] = False
                
        except Exception as e:
            logger.error(f"Error in place_order_with_oco: {e}")
            result['error'] = str(e)
            
        return result

    # ========================================================================
    # L4 FIX: Currency conversion and best trading pair finder
    # ========================================================================
    
    async def find_best_trading_pair(self, base_currency: str, user_balances: Dict[str, float]) -> Optional[str]:
        """
        Find the best trading pair for a base currency based on user's available balances.
        
        L4 FIX: If user has EUR but wants to trade BTC/USDT, this finds alternative pairs
        like BTC/EUR that the user can actually trade.
        
        Args:
            base_currency: The base currency (e.g., 'BTC', 'ETH')
            user_balances: Dict of user's available balances {currency: amount}
            
        Returns:
            Best available trading pair symbol or None if none available
        """
        # Priority order for quote currencies
        quote_priority = ['USDT', 'USDC', 'BUSD', 'USD', 'EUR', 'ZUSD', 'ZEUR']
        
        # Get user's available currencies (with meaningful balance)
        available_currencies = [
            curr for curr, balance in user_balances.items() 
            if balance > 10  # At least $10 equivalent
        ]
        
        # Load markets
        await self.exchange.load_markets()
        
        # Find best pair
        for quote in quote_priority:
            if quote in available_currencies:
                potential_symbol = f"{base_currency}/{quote}"
                if potential_symbol in self.exchange.markets:
                    market = self.exchange.markets[potential_symbol]
                    if market.get('active', True):
                        logger.info(f"✅ L4 FIX: Found trading pair {potential_symbol} for {base_currency}")
                        return potential_symbol
        
        # Fallback: check all available markets for this base
        for symbol, market in self.exchange.markets.items():
            if symbol.startswith(f"{base_currency}/") and market.get('active', True):
                quote = symbol.split('/')[1]
                if quote in available_currencies:
                    logger.info(f"✅ L4 FIX: Found alternative pair {symbol}")
                    return symbol
        
        logger.warning(f"⚠️ L4: No tradeable pair found for {base_currency} with available currencies: {available_currencies}")
        return None

    async def suggest_currency_conversion(
        self, 
        target_symbol: str, 
        user_balances: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Suggest currency conversion if user cannot trade desired pair.
        
        L4 FIX: Returns suggestion for converting user's available currency
        to the required quote currency.
        
        Args:
            target_symbol: Desired trading pair (e.g., 'BTC/USDT')
            user_balances: User's available balances
            
        Returns:
            Dict with: can_trade, suggestion, conversion_needed, conversion_pair
        """
        base, quote = target_symbol.split('/')
        
        # Check if user has the quote currency
        user_quote_balance = user_balances.get(quote, 0)
        
        if user_quote_balance > 10:
            return {
                'can_trade': True,
                'suggestion': None,
                'conversion_needed': False,
            }
        
        # Find what currency the user has
        available = [(curr, bal) for curr, bal in user_balances.items() if bal > 10]
        
        if not available:
            return {
                'can_trade': False,
                'suggestion': 'No sufficient balance in any currency',
                'conversion_needed': False,
            }
        
        # Get best available currency
        best_currency, best_balance = max(available, key=lambda x: x[1])
        
        # Check for conversion pair
        conversion_pairs = [
            f"{best_currency}/{quote}",
            f"{quote}/{best_currency}",
        ]
        
        await self.exchange.load_markets()
        
        for conv_pair in conversion_pairs:
            if conv_pair in self.exchange.markets:
                return {
                    'can_trade': False,
                    'suggestion': f"Convert {best_currency} to {quote} using {conv_pair} first",
                    'conversion_needed': True,
                    'conversion_pair': conv_pair,
                    'from_currency': best_currency,
                    'from_balance': best_balance,
                    'to_currency': quote,
                }
        
        # Check for alternative trading pair
        alt_pair = await self.find_best_trading_pair(base, user_balances)
        if alt_pair:
            return {
                'can_trade': True,
                'suggestion': f"Use {alt_pair} instead of {target_symbol}",
                'conversion_needed': False,
                'alternative_pair': alt_pair,
            }
        
        return {
            'can_trade': False,
            'suggestion': f"Cannot trade {target_symbol}. Need {quote} but only have: {list(user_balances.keys())}",
            'conversion_needed': True,
        }

    async def get_tradeable_balance_for_symbol(
        self, 
        symbol: str
    ) -> Dict[str, Any]:
        """
        Get tradeable balance for a specific symbol.
        
        L4 FIX: Returns the available balance in the correct quote currency
        for the given trading pair.
        
        Returns:
            Dict with: balance, currency, can_trade, suggestion
        """
        try:
            balance = await self.exchange.fetch_balance()
            _, quote = symbol.split('/')
            
            # Map quote currencies (Kraken uses different names)
            quote_variants = [quote]
            if quote == 'USD':
                quote_variants.extend(['ZUSD', 'USDT', 'USDC'])
            elif quote == 'EUR':
                quote_variants.extend(['ZEUR'])
            elif quote == 'USDT':
                quote_variants.extend(['USDC', 'BUSD'])
            
            # Find best available balance
            best_balance = 0
            best_currency = quote
            
            for q in quote_variants:
                bal = float(balance.get('free', {}).get(q, 0) or 0)
                if bal > best_balance:
                    best_balance = bal
                    best_currency = q
            
            # Prepare user balances for suggestion
            user_balances = {k: float(v or 0) for k, v in balance.get('free', {}).items() if float(v or 0) > 0}
            
            if best_balance < 10:
                # Not enough balance - get suggestion
                suggestion = await self.suggest_currency_conversion(symbol, user_balances)
                return {
                    'balance': best_balance,
                    'currency': best_currency,
                    'can_trade': suggestion.get('can_trade', False),
                    'suggestion': suggestion.get('suggestion'),
                    'alternative_pair': suggestion.get('alternative_pair'),
                }
            
            return {
                'balance': best_balance,
                'currency': best_currency,
                'can_trade': True,
                'suggestion': None,
            }
            
        except Exception as e:
            logger.error(f"Error getting tradeable balance: {e}")
            return {
                'balance': 0,
                'currency': 'USDT',
                'can_trade': False,
                'suggestion': str(e),
            }

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
