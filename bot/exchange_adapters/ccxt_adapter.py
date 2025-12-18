"""
Adapter dla CCXT - uniwersalna biblioteka do 100+ giełd crypto.
Użyj tego zamiast PrimeXBT jeśli nie mają API.
"""

import ccxt
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
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
        margin: bool = False  # NEW: Margin trading mode
    ):
        if exchange_name not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"Exchange {exchange_name} not supported. Use: {list(self.SUPPORTED_EXCHANGES.keys())}")
            
        exchange_class = self.SUPPORTED_EXCHANGES[exchange_name]
        
        # Determine market type
        if margin:
            market_type = 'margin'
        elif futures:
            market_type = 'future'
        else:
            market_type = 'spot'
        
        config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'timeout': REQUEST_TIMEOUT,
            'options': {
                'adjustForTimeDifference': True,
                'defaultType': market_type,
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
        self.margin = margin  # NEW: Track margin mode
        self._rate_limited_until = None  # Track rate limit cooldown
        
        # Symbol validation cache
        self._valid_symbols: Set[str] = set()
        self._symbols_loaded = False
        self._symbols_lock = asyncio.Lock()
    
    async def _ensure_symbols_loaded(self) -> None:
        """Ensure exchange symbols/markets are loaded."""
        async with self._symbols_lock:
            if not self._symbols_loaded:
                try:
                    await self.exchange.load_markets()
                    self._valid_symbols = set(self.exchange.symbols)
                    self._symbols_loaded = True
                    logger.info(f"✅ Loaded {len(self._valid_symbols)} symbols from {self.exchange.id}")
                except Exception as e:
                    logger.warning(f"Failed to load markets: {e}")
    
    async def validate_symbol(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a symbol is tradeable on this exchange.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        await self._ensure_symbols_loaded()
        
        if not self._valid_symbols:
            # Couldn't load symbols - allow but warn
            logger.warning(f"Symbol validation skipped - markets not loaded")
            return True, None
        
        # Direct match
        if symbol in self._valid_symbols:
            return True, None
        
        # Try common transformations
        # e.g., BTCUSDT -> BTC/USDT
        normalized = symbol
        if '/' not in symbol:
            # Try adding slash before common quote currencies
            for quote in ['USDT', 'USDC', 'USD', 'EUR', 'BTC', 'ETH']:
                if symbol.endswith(quote):
                    normalized = f"{symbol[:-len(quote)]}/{quote}"
                    if normalized in self._valid_symbols:
                        logger.debug(f"Symbol normalized: {symbol} -> {normalized}")
                        return True, None
        
        # Not found
        similar = [s for s in self._valid_symbols if symbol.split('/')[0] in s][:5]
        suggestion = f" Similar: {similar}" if similar else ""
        return False, f"Symbol '{symbol}' not found on {self.exchange.id}.{suggestion}"
    
    async def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get symbol trading info (min order size, price precision, etc.)
        
        Returns:
            Dict with 'min_amount', 'min_cost', 'price_precision', 'amount_precision'
            or None if symbol not found
        """
        await self._ensure_symbols_loaded()
        
        try:
            if symbol not in self.exchange.markets:
                return None
            
            market = self.exchange.markets[symbol]
            limits = market.get('limits', {})
            precision = market.get('precision', {})
            
            return {
                'min_amount': float(limits.get('amount', {}).get('min', 0) or 0),
                'min_cost': float(limits.get('cost', {}).get('min', 0) or 0),
                'max_amount': float(limits.get('amount', {}).get('max', float('inf')) or float('inf')),
                'price_precision': precision.get('price', 8),
                'amount_precision': precision.get('amount', 8),
                'contract_size': float(market.get('contractSize', 1) or 1),
                'type': market.get('type', 'spot'),
            }
        except Exception as e:
            logger.warning(f"Failed to get symbol info for {symbol}: {e}")
            return None
    
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
        """Get balance for a specific currency."""
        try:
            params = {'type': 'margin'} if self.margin else {}
            balance = await self._retry_async(self.exchange.fetch_balance, params)
            return balance['total'].get(currency, 0.0)
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error fetching {currency} balance: {e}")
            return 0.0

    async def get_all_balances(self) -> Dict[str, float]:
        """Get all non-zero balances."""
        try:
            params = {'type': 'margin'} if self.margin else {}
            balance = await self._retry_async(self.exchange.fetch_balance, params)
            return {k: v for k, v in balance['total'].items() if v > 0}
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error fetching all balances: {e}")
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
        """Get account balance and info. Supports multiple stablecoins."""
        try:
            # For margin mode, fetch margin balance
            if self.margin:
                balance = await self.exchange.fetch_balance({'type': 'margin'})
            else:
                balance = await self.exchange.fetch_balance()
            
            # Try multiple stablecoins in order of preference
            stablecoins = ['USDT', 'USDC', 'USD', 'BUSD']
            
            free_total = 0.0
            total_total = 0.0
            used_total = 0.0
            
            for coin in stablecoins:
                free_total += float(balance['free'].get(coin, 0) or 0)
                total_total += float(balance['total'].get(coin, 0) or 0)
                used_total += float(balance['used'].get(coin, 0) or 0)
            
            return AccountInfo(
                free=free_total,
                total=total_total,
                used=used_total,
            )
        except ccxt.NetworkError as e:
            print(f"Network error fetching account info: {e}")
            raise
        except ccxt.ExchangeError as e:
            print(f"Exchange error fetching account info: {e}")
            raise

    async def get_margin_info(self) -> Dict[str, Any]:
        """
        Get margin/leverage trading information.
        P1 FIX: Added for proper margin level checking.
        P0 FIX 2025-12-13: Use spot balance as fallback when margin fields are 0.
        
        Returns:
            Dict with 'free_margin', 'used_margin', 'margin_level', 'can_trade'
        """
        try:
            balance = await self.exchange.fetch_balance()
            
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
        P1 FIX: Added for proper margin validation before placing orders.
        
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
            
            # Check if margin trading is allowed
            if not can_trade:
                return {
                    'can_open': False,
                    'reason': f"Margin level too low ({margin_level:.0f}%, need >150%)",
                    'available_margin': free_margin,
                    'required_margin': required_margin,
                    'suggestion': 'Close some positions or add funds to increase margin level',
                }
            
            # Check if enough free margin
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

    async def get_spot_balances(self, min_value_usd: float = 10.0) -> List[str]:
        """
        Get list of non-stablecoin assets with positive balance.
        
        FIXED 2025-12-16: 
        - Increased default min_value_usd to $10 to filter dust/airdrops
        - Added exclusion for Binance Launchpad tokens (LD*)
        - These are NOT active trading positions
        
        Args:
            min_value_usd: Minimum USD value to include (default $10)
        """
        try:
            balance = await self.exchange.fetch_balance()
            # Exclude common stablecoins and fiat
            excluded_assets = {'USDT', 'USDC', 'USD', 'DAI', 'BUSD', 'EUR', 'PLN', 'GBP', 'CHF', 'USDG'}
            
            # Exclude Binance Launchpad/Earn tokens (start with LD)
            # These are locked staking positions, NOT active trades
            LAUNCHPAD_PREFIXES = ('LD', 'B', 'BETH', 'WBETH')
            
            # Minimum absolute quantity threshold
            DUST_THRESHOLD = 0.0001
            
            assets = []
            for asset, amount in balance['total'].items():
                if amount <= 0 or asset in excluded_assets:
                    continue
                
                # Skip Binance Launchpad/Earn tokens
                if asset.startswith('LD'):
                    logger.debug(f"🧹 get_spot_balances: Skipping Launchpad token {asset}")
                    continue
                    
                # Skip dust quantities
                if amount < DUST_THRESHOLD:
                    continue
                
                # Try to check USD value to filter dust
                try:
                    quote = 'USDC' if self.exchange.id == 'kraken' else 'USDT'
                    symbol = f"{asset}/{quote}"
                    ticker = await self.exchange.fetch_ticker(symbol)
                    value_usd = amount * ticker['last']
                    
                    if value_usd < min_value_usd:
                        logger.debug(f"🧹 get_spot_balances: Skipping {asset} worth ${value_usd:.2f} (< ${min_value_usd})")
                        continue
                        
                    assets.append(asset)
                except Exception:
                    # If can't get price, skip (likely illiquid/unlisted token)
                    logger.debug(f"🧹 get_spot_balances: Skipping {asset} (no price available)")
                    continue
                    
            return assets
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            logger.error(f"Error fetching spot balances: {e}")
            return []

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get open positions. For margin mode, returns borrowed positions from balance."""
        try:
            # Debug: Log which exchange and mode
            logger.debug(f"get_positions called: exchange={self.exchange.id}, margin={self.margin}, futures={self.futures}")
            
            # Margin mode: Get positions from borrowed balances
            if self.margin:
                logger.debug("Using margin mode - calling _get_margin_positions()")
                return await self._get_margin_positions()
            
            # Kraken/Spot mode: Get positions from spot balances with entry price from trades
            if self.exchange.id == 'kraken':
                logger.debug("Using Kraken spot mode - calling _get_spot_positions_with_entry_price()")
                return await self._get_spot_positions_with_entry_price()
            
            # Binance SPOT mode (not futures): Use spot balances like Kraken
            if self.exchange.id == 'binance' and not self.futures:
                logger.debug("Using Binance SPOT mode - calling _get_spot_positions_with_entry_price()")
                return await self._get_spot_positions_with_entry_price()
            
            # Futures mode: Use fetch_positions
            logger.debug(f"Using futures mode - calling fetch_positions for {self.exchange.id}")
            positions_raw = await self.exchange.fetch_positions(symbols=[symbol] if symbol else None)
            
            valid_positions = []
            for pos in positions_raw:
                if not pos.get('contracts') or pos['contracts'] <= 0:
                    continue
                    
                # P0-NEW-3 FIX: Validate entry_price is not 0
                entry_price = float(pos.get('entryPrice') or pos.get('markPrice') or 0.0)
                
                if entry_price <= 0:
                    # Try to get current market price as fallback
                    try:
                        ticker = await self.exchange.fetch_ticker(pos['symbol'])
                        entry_price = float(ticker.get('last', 0))
                        logger.warning(
                            f"⚠️ Position {pos['symbol']} had entry_price=0, using market price: {entry_price}"
                        )
                    except Exception as ticker_err:
                        logger.error(
                            f"🚨 CRITICAL: Position {pos['symbol']} has entry_price=0 and cannot fetch market price! "
                            f"P&L calculations will be incorrect. Error: {ticker_err}"
                        )
                        # Still add position but mark issue
                        entry_price = 0.0
                
                valid_positions.append(Position(
                    symbol=pos['symbol'],
                    side=pos['side'],
                    quantity=pos['contracts'],
                    entry_price=entry_price,
                    unrealized_pnl=pos.get('unrealizedPnl', 0) or 0,
                    leverage=pos.get('leverage', 1)
                ))
            
            return valid_positions
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            print(f"Error fetching positions: {e}")
            return []
    
    async def _get_spot_positions_with_entry_price(self) -> List[Position]:
        """
        Get spot positions from balance with calculated entry price from trade history.
        Used for Kraken and other spot exchanges.
        
        FIX 2025-12-16:
        - Filters out dust positions (below exchange minimum)
        - Excludes Binance Launchpad/Earn tokens (LD*) - these are NOT trading positions
        - Increased min value to $10 to avoid counting airdrops/dust
        """
        try:
            balance = await self.exchange.fetch_balance()
            positions = []
            
            # Exclude stablecoins and fiat
            excluded_assets = {'USDT', 'USDC', 'USD', 'DAI', 'BUSD', 'EUR', 'PLN', 'GBP', 'CHF', 'USDG'}
            
            # P0 FIX: Thresholds for dust detection
            DUST_THRESHOLD = 0.0001  # Absolute minimum quantity
            MIN_VALUE_USD = 10.0  # Minimum position value in USD (increased from $1)
            
            for asset, data in balance.items():
                if isinstance(data, dict):
                    total = float(data.get('total', 0) or 0)
                    
                    # If asset has positive balance (not stablecoins), it's a LONG position
                    if total > 0 and asset not in excluded_assets:
                        # FIX 2025-12-16: Skip Binance Launchpad/Earn tokens (LD*)
                        # These are locked staking positions, NOT active trades
                        if asset.startswith('LD'):
                            logger.debug(f"🧹 Skipping Launchpad token: {asset}")
                            continue
                        
                        # P0 FIX: Skip absolute dust quantities
                        if total < DUST_THRESHOLD:
                            logger.debug(f"🧹 Skipping dust balance: {asset} qty={total:.10f}")
                            continue
                        
                        # Try to get entry price from recent trades
                        entry_price = await self._calculate_entry_price_from_trades(asset, total)
                        
                        # Determine quote currency (USDC for Kraken)
                        quote = 'USDC' if self.exchange.id == 'kraken' else 'USDT'
                        symbol = f"{asset}/{quote}"
                        
                        # Get current price for unrealized P&L and value check
                        try:
                            ticker = await self.exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            unrealized_pnl = (current_price - entry_price) * total if entry_price > 0 else 0.0
                            
                            # P0 FIX: Check position value - skip if below minimum
                            position_value = total * current_price
                            if position_value < MIN_VALUE_USD:
                                logger.debug(
                                    f"🧹 Skipping low-value position: {symbol} qty={total:.6f} "
                                    f"worth ${position_value:.4f} (< ${MIN_VALUE_USD})"
                                )
                                continue
                        except:
                            current_price = entry_price
                            unrealized_pnl = 0.0
                            # If we can't get price, skip - likely illiquid/unlisted token
                            logger.debug(f"🧹 Skipping {asset} (no price available)")
                            continue
                        
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
    
    async def _calculate_entry_price(self, asset: str, current_qty: float) -> float:
        """
        Calculate weighted average entry price from recent buy trades.
        Alias for _calculate_entry_price_from_trades for backwards compatibility.
        """
        return await self._calculate_entry_price_from_trades(asset, current_qty)
    
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
        """Get margin positions from borrowed balances (for Binance Margin).
        
        v2.0 FIX: Now properly calculates entry_price using trade history.
        """
        try:
            balance = await self.exchange.fetch_balance({'type': 'margin'})
            positions = []
            
            for asset, data in balance.items():
                if isinstance(data, dict):
                    borrowed = float(data.get('borrowed', 0) or 0)
                    free = float(data.get('free', 0) or 0)
                    
                    # If asset is borrowed, it's a SHORT position
                    if borrowed > 0:
                        # Determine trading pair (assuming USDT as quote)
                        symbol = f"{asset}/USDT"
                        
                        # FIX: Calculate entry price from trade history
                        entry_price = await self._calculate_entry_price(asset, borrowed)
                        if entry_price <= 0:
                            # Fallback: get current price
                            try:
                                ticker = await self.exchange.fetch_ticker(symbol)
                                entry_price = ticker.get('last', 0)
                                logger.warning(f"Using current price as entry for SHORT {asset}: {entry_price}")
                            except:
                                entry_price = 0
                        
                        # Calculate unrealized PnL for short
                        try:
                            ticker = await self.exchange.fetch_ticker(symbol)
                            current_price = ticker.get('last', 0)
                            if entry_price > 0 and current_price > 0:
                                unrealized_pnl = (entry_price - current_price) * borrowed  # Short profit when price drops
                            else:
                                unrealized_pnl = 0.0
                        except:
                            unrealized_pnl = 0.0
                        
                        positions.append(Position(
                            symbol=symbol,
                            side='short',
                            quantity=borrowed,
                            entry_price=entry_price,
                            unrealized_pnl=unrealized_pnl,
                            leverage=1
                        ))
                        
                    # If asset has positive free balance (not USDT/USDC), it's a LONG position
                    elif free > 0 and asset not in ['USDT', 'USDC', 'USD', 'BUSD']:
                        symbol = f"{asset}/USDT"
                        
                        # FIX: Calculate entry price from trade history
                        entry_price = await self._calculate_entry_price(asset, free)
                        if entry_price <= 0:
                            # Fallback: get current price
                            try:
                                ticker = await self.exchange.fetch_ticker(symbol)
                                entry_price = ticker.get('last', 0)
                                logger.warning(f"Using current price as entry for LONG {asset}: {entry_price}")
                            except:
                                entry_price = 0
                        
                        # Calculate unrealized PnL for long
                        try:
                            ticker = await self.exchange.fetch_ticker(symbol)
                            current_price = ticker.get('last', 0)
                            if entry_price > 0 and current_price > 0:
                                unrealized_pnl = (current_price - entry_price) * free  # Long profit when price rises
                            else:
                                unrealized_pnl = 0.0
                        except:
                            unrealized_pnl = 0.0
                        
                        positions.append(Position(
                            symbol=symbol,
                            side='long',
                            quantity=free,
                            entry_price=entry_price,
                            unrealized_pnl=unrealized_pnl,
                            leverage=1
                        ))
            
            return positions
        except Exception as e:
            print(f"Error fetching margin positions: {e}")
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
        """Place an order with optional SL/TP and auto-adjusted leverage."""
        
        try:
            # P1 FIX: Validate symbol before placing order
            is_valid, error_msg = await self.validate_symbol(symbol)
            if not is_valid:
                logger.error(f"❌ Invalid symbol: {error_msg}")
                raise ccxt.BadSymbol(error_msg)
            
            # P1 FIX: Validate order parameters
            symbol_info = await self.get_symbol_info(symbol)
            if symbol_info:
                min_amount = symbol_info.get('min_amount', 0)
                min_cost = symbol_info.get('min_cost', 0)
                
                if quantity < min_amount:
                    logger.error(
                        f"❌ Order quantity {quantity} below minimum {min_amount} for {symbol}"
                    )
                    raise ccxt.InvalidOrder(
                        f"Quantity {quantity} below minimum {min_amount}"
                    )
                
                # Estimate order cost
                order_price = price if price else (await self.exchange.fetch_ticker(symbol))['last']
                order_cost = quantity * order_price
                
                if order_cost < min_cost and min_cost > 0:
                    logger.error(
                        f"❌ Order cost ${order_cost:.2f} below minimum ${min_cost:.2f} for {symbol}"
                    )
                    raise ccxt.InvalidOrder(
                        f"Order cost ${order_cost:.2f} below minimum ${min_cost:.2f}"
                    )
            
            params = {}
            actual_leverage = 1
            
            # Binance Margin mode: Set margin type in params
            if self.exchange.id == 'binance' and self.margin and not self.futures:
                params['type'] = 'margin'  # Required for Binance margin trading
                params['marginMode'] = 'cross'  # Use cross margin (can be 'isolated' if needed)
                logger.info(f"📊 Binance MARGIN order: {symbol} {side} {quantity} (cross margin)")
            
            # Set leverage if specified - use safe method with fallback
            if leverage and self.futures:
                if self.exchange.id == 'kraken':
                    # Kraken: get best available leverage and pass in params
                    actual_leverage = await self.get_best_leverage(symbol, leverage)
                    params['leverage'] = actual_leverage
                else:
                    # Other exchanges: try to set leverage with fallback
                    actual_leverage = await self.set_leverage_safe(symbol, leverage)
                    
                logger.info(f"📊 {symbol}: Using {actual_leverage}x leverage (requested: {leverage}x)")
            print(f"DEBUG: place_order for {self.exchange.id} - SL={stop_loss}, TP={take_profit}")
            
            # Exchange-specific SL/TP params
            if stop_loss or take_profit:
                if self.exchange.id == 'binance':
                    # Binance SPOT/MARGIN: SL/TP not supported in single order
                    if not self.futures:
                        logger.info(f"📊 Binance SPOT/MARGIN: SL/TP will be monitored by Position Monitor (SL={stop_loss}, TP={take_profit})")
                        # Don't add SL/TP params - not supported
                    else:
                        # Binance FUTURES: Use unified stopLoss/takeProfit
                        if stop_loss:
                            params['stopLoss'] = {'type': 'market', 'triggerPrice': stop_loss}
                        if take_profit:
                            params['takeProfit'] = {'type': 'market', 'triggerPrice': take_profit}
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
                elif self.exchange.id == 'kraken':
                    # Kraken SPOT: Does NOT support SL/TP in order params
                    # SL/TP will be handled by Position Monitor (software-side)
                    logger.info(f"📊 Kraken SPOT: SL/TP will be monitored by Position Monitor (SL={stop_loss}, TP={take_profit})")
                    # Don't add anything to params - Kraken doesn't support it
                else:
                    # Generic CCXT unified format (for exchanges that support it)
                    if stop_loss:
                        params['stopLoss'] = {'type': 'market', 'price': stop_loss}
                    if take_profit:
                        params['takeProfit'] = {'type': 'market', 'price': take_profit}

            # FIX: Handle reduce_only parameter for closing positions
            # SPOT mode doesn't support reduceOnly, only Futures/Margin do
            # KRAKEN FIX: Kraken SPOT/Margin API doesn't support reduceOnly at all
            if reduce_only:
                if self.exchange.id == 'kraken':
                    # Kraken doesn't support reduceOnly even in margin mode via spot API
                    logger.debug(f"📊 Ignoring reduce_only for Kraken (not supported via spot API)")
                elif self.futures or self.margin:
                    params['reduceOnly'] = True
                    logger.debug(f"📊 Adding reduceOnly=True for {self.exchange.id} Futures/Margin close")
                else:
                    # SPOT mode - ignore reduce_only, not supported
                    logger.debug(f"📊 Ignoring reduce_only for {self.exchange.id} SPOT mode (not supported)")

            print(f"DEBUG: place_order for {self.exchange.id} params: {params}")
            if order_type.lower() == 'market':
                order_raw = await self.exchange.create_market_order(symbol, side, quantity, None, params)
            else:  # limit
                if not price:
                    raise ValueError("Price required for limit orders")
                order_raw = await self.exchange.create_limit_order(symbol, side, quantity, price, params)
            
            # Log SL/TP info
            if stop_loss or take_profit:
                print(f"DEBUG: Order placed with SL={stop_loss}, TP={take_profit}")
            
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
                
                # FIX: Binance SPOT doesn't support reduceOnly parameter
                if self.exchange.id == 'binance' and not self.futures and not self.margin:
                    # SPOT mode: Just sell the asset, no special params
                    logger.info(f"📊 Closing SPOT position: {symbol} | {side.upper()} {pos.quantity}")
                elif self.futures or self.margin:
                    # Futures/Margin mode: Use reduceOnly
                    params['reduceOnly'] = True
                    logger.info(f"📊 Closing Futures/Margin position: {symbol} | {side.upper()} {pos.quantity} (reduceOnly)")
                else:
                    # Other exchanges in SPOT mode - also no reduceOnly
                    logger.info(f"📊 Closing SPOT position: {symbol} | {side.upper()} {pos.quantity}")
                
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
        
        # P1-NEW-2 FIX: Validate leverage range before attempting to set
        MAX_SAFE_LEVERAGE = 125  # Most exchanges cap at 125x
        MIN_LEVERAGE = 1
        
        if not isinstance(desired_leverage, (int, float)):
            logger.warning(f"⚠️ Invalid leverage type: {type(desired_leverage)}, defaulting to 1x")
            return 1
        
        desired_leverage = int(desired_leverage)
        
        if desired_leverage < MIN_LEVERAGE:
            logger.warning(f"⚠️ Leverage {desired_leverage} below minimum, using {MIN_LEVERAGE}x")
            desired_leverage = MIN_LEVERAGE
        elif desired_leverage > MAX_SAFE_LEVERAGE:
            logger.warning(f"⚠️ Leverage {desired_leverage}x exceeds safe maximum ({MAX_SAFE_LEVERAGE}x), capping")
            desired_leverage = MAX_SAFE_LEVERAGE
        
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
