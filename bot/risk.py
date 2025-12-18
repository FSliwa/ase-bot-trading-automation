from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import AppConfig


@dataclass
class RiskAssessment:
    ok: bool
    reason: Optional[str] = None


def validate_order(
    *,
    is_live: bool,
    config: AppConfig,
    side: str,
    symbol: str,
    quantity: float,
    leverage: Optional[float],
    stop_loss: Optional[float],
) -> RiskAssessment:
    """Validate order against basic risk rules."""
    if leverage is not None and leverage > config.max_leverage:
        return RiskAssessment(ok=False, reason=f"Leverage {leverage}x exceeds max {config.max_leverage}x")

    if is_live and config.require_stop_loss_live and stop_loss is None:
        return RiskAssessment(ok=False, reason="Stop-loss is required in live mode")

    if quantity <= 0:
        return RiskAssessment(ok=False, reason="Quantity must be positive")

    # Minimal symbol validation: must be uppercase alnum
    if not symbol or not symbol.isupper():
        return RiskAssessment(ok=False, reason="Symbol must be provided in uppercase (e.g., BTCUSDT)")

    return RiskAssessment(ok=True)


