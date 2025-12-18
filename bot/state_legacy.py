from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any, Dict, List

from .broker.paper import PaperBroker, Position, OrderFill


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def save_broker_state(broker: PaperBroker, path: str) -> None:
    data: Dict[str, Any] = {
        "positions": {sym: asdict(pos) for sym, pos in broker.positions.items()},
        "fills": [asdict(f) for f in broker.fills],
    }
    _ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_broker_state(broker: PaperBroker, path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    positions_raw: Dict[str, Dict[str, Any]] = data.get("positions", {})
    fills_raw: List[Dict[str, Any]] = data.get("fills", [])

    broker.positions.clear()
    for sym, pos in positions_raw.items():
        broker.positions[sym] = Position(
            symbol=pos["symbol"],
            side=pos["side"],
            quantity=float(pos["quantity"]),
            entry_price=float(pos["entry_price"]),
            leverage=float(pos.get("leverage", 1.0)),
            stop_loss=pos.get("stop_loss"),
            take_profit=pos.get("take_profit"),
        )

    broker.fills.clear()
    for fr in fills_raw:
        broker.fills.append(
            OrderFill(
                symbol=fr["symbol"],
                side=fr["side"],
                quantity=float(fr["quantity"]),
                price=float(fr["price"]),
                order_type=fr["order_type"],
                tif=fr.get("tif"),
                reduce_only=bool(fr.get("reduce_only", False)),
            )
        )


