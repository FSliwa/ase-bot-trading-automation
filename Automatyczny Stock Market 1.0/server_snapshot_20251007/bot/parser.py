from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeIntent:
    side: Optional[str]  # "buy" | "sell"
    symbol: Optional[str]
    order_type: Optional[str]  # "market" | "limit"
    quantity: Optional[float]
    price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    leverage: Optional[float]
    tif: Optional[str]  # GTC | IOC | FOK
    reduce_only: bool
    raw: str


_SIDE_MAP = {
    "buy": "buy",
    "kup": "buy",
    "long": "buy",
    "sell": "sell",
    "sprzedaj": "sell",
    "short": "sell",
}


def _find_first(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def _find_bool(pattern: str, text: str, flags: int = re.IGNORECASE) -> bool:
    return re.search(pattern, text, flags) is not None


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except Exception:
        return None


def parse_trade_intent(command: str) -> TradeIntent:
    text = command.strip()

    # side
    side = None
    for key, mapped in _SIDE_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", text, re.IGNORECASE):
            side = mapped
            break

    # quantity
    qty = _to_float(_find_first(r"\b(\d+(?:[\.,]\d+)?)\b", text))

    # symbol: prefer uppercase tokens not in reserved keywords
    reserved = {
        "BUY", "KUP", "SELL", "SPRZEDAJ", "LONG", "SHORT",
        "MARKET", "LIMIT", "SL", "STOP", "LOSS", "TP", "TAKE", "PROFIT",
        "LEV", "LEVERAGE", "DŹWIGNIA", "TIF", "GTC", "IOC", "FOK",
        "REDUCE", "ONLY", "REDUCE-ONLY",
    }
    tokens = re.findall(r"\b[A-Z0-9]{3,}\b", text.upper())
    symbol = None
    for tok in tokens:
        if tok not in reserved:
            symbol = tok
            break

    # order type and price
    order_type = None
    price = None
    if re.search(r"\bmarket\b", text, re.IGNORECASE):
        order_type = "market"
    elif re.search(r"\blimit\b", text, re.IGNORECASE):
        order_type = "limit"
        price = _to_float(_find_first(r"\blimit\s+(\d+(?:[\.,]\d+)?)\b", text))

    # SL / TP
    stop_loss = _to_float(_find_first(r"\b(?:sl|stop[- ]?loss)\s*(\d+(?:[\.,]\d+)?)\b", text))
    take_profit = _to_float(_find_first(r"\b(?:tp|take[- ]?profit)\s*(\d+(?:[\.,]\d+)?)\b", text))

    # leverage: e.g., lev 3x or leverage 3x
    leverage = _to_float(_find_first(r"\b(?:lev|leverage|d[zź]wignia)\s*(\d+(?:[\.,]\d+)?)x\b", text))

    # tif: gtc|ioc|fok
    tif = _find_first(r"\b(tif\s*(gtc|ioc|fok)|gtc|ioc|fok)\b", text)
    if tif:
        tif = tif.split()[-1].upper()

    # reduce-only flag
    reduce_only = _find_bool(r"\breduce[- ]?only\b", text)

    return TradeIntent(
        side=side,
        symbol=symbol,
        order_type=order_type,
        quantity=qty,
        price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        leverage=leverage,
        tif=tif,
        reduce_only=reduce_only,
        raw=command,
    )


