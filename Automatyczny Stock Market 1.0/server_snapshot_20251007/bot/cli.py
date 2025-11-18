from __future__ import annotations

import sys
from typing import Optional

import typer
from rich import print
from rich.table import Table

from .config import ensure_live_confirmation, load_config
from .logging_setup import get_logger
from .parser import parse_trade_intent
from .risk import RiskAssessment, validate_order
from .broker.enhanced_paper import EnhancedPaperBroker
from .db import init_db as initialize_db


app = typer.Typer(add_completion=False, no_args_is_help=True)
logger = get_logger("bot.cli")

# Use the enhanced broker with database persistence
broker = EnhancedPaperBroker()

@app.command("init-db")
def init_db_command():
    """Initialize the trading database."""
    try:
        initialize_db()
        print("[green]Database initialized successfully.[/green]")
    except Exception as e:
        print(f"[red]Database initialization failed: {e}[/red]")
        raise typer.Exit(code=1)

@app.command("trade")
def trade(
    command: str = typer.Argument(..., help="Natural language command (PL/EN)."),
    price: Optional[float] = typer.Option(None, help="Simulated market price for market orders (paper)."),
    live: bool = typer.Option(False, "--live", help="Enable live trading (gated)."),
    confirm_yes: bool = typer.Option(False, "--confirm-yes", help="Confirm live mode explicitly."),
):
    """Place an order from natural language command.

    In MVP this executes against in-memory PaperBroker unless --live is provided
    and confirmation gate passes. Live mode isn't implemented; HTTP client methods
    raise NotImplementedError.
    """
    config = load_config()
    ensure_live_confirmation(live, confirm_yes)

    intent = parse_trade_intent(command)

    if not intent.side or not intent.symbol or not intent.quantity or not intent.order_type:
        typer.echo("[red]Nie udało się sparsować polecenia. Upewnij się, że podano: side, qty, symbol, type.[/red]")
        raise typer.Exit(code=2)

    assessment: RiskAssessment = validate_order(
        is_live=live,
        config=config,
        side=intent.side,
        symbol=intent.symbol,
        quantity=intent.quantity,
        leverage=intent.leverage,
        stop_loss=intent.stop_loss,
    )
    if not assessment.ok:
        typer.echo(f"[red]Zlecenie odrzucone przez risk managera: {assessment.reason}[/red]")
        raise typer.Exit(code=3)

    if live:
        typer.echo("[yellow]Tryb live niezaimplementowany w MVP (HTTP client NotImplementedError).[/yellow]")
        raise typer.Exit(code=4)

    # Update market price for paper trading simulation if provided
    if price and intent.symbol:
        broker.update_market_price(intent.symbol, price)

    try:
        result = broker.place_order(
            side=intent.side.upper(),
            symbol=intent.symbol,
            order_type=intent.order_type.upper(),
            quantity=intent.quantity,
            price=intent.price,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            reduce_only=intent.reduce_only,
            leverage=intent.leverage,
            time_in_force=intent.tif or "GTC",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Order failed")
        typer.echo(f"[red]Order failed: {exc}[/red]")
        raise typer.Exit(code=5)

    if result.get("success"):
        print(f"[green]OK[/green] Order {result.get('status')}: {result.get('message')}")
        if result.get("bracket_orders"):
            print(f"Bracket orders created: {result['bracket_orders']}")
    else:
        print(f"[red]Error placing order: {result.get('error')}[/red]")


@app.command("status")
def status():
    pos = broker.get_open_positions()
    if not pos:
        typer.echo("Brak otwartych pozycji.")
        raise typer.Exit(code=0)

    table = Table("Symbol", "Side", "Qty", "Entry", "Current", "Leverage", "Unrealized PnL", "SL", "TP")
    for p in pos:
        pnl_color = "green" if p['unrealized_pnl'] >= 0 else "red"
        table.add_row(
            p['symbol'],
            p['side'],
            str(p['quantity']),
            f"{p['entry_price']:.2f}",
            f"{p['current_price']:.2f}",
            f"{p['leverage']:.1f}x",
            f"[{pnl_color}]{p['unrealized_pnl']:.2f}[/{pnl_color}]",
            str(p.get('stop_loss') or '-'),
            str(p.get('take_profit') or '-'),
        )
    print(table)


@app.command("close-position")
def close_position(
    symbol: str = typer.Argument(..., help="Symbol, np. BTCUSDT"),
    quantity: Optional[float] = typer.Option(None, help="Quantity to close. Defaults to full position."),
):
    result = broker.close_position(symbol=symbol, quantity=quantity)
    if result.get("success"):
        typer.echo(f"Zamknięto pozycję {symbol}. Status: {result.get('message')}")
    else:
        typer.echo(f"[red]Błąd podczas zamykania pozycji: {result.get('error')}[/red]")


@app.command("orders")
def orders():
    open_orders = broker.get_open_orders()
    if not open_orders:
        typer.echo("Brak otwartych zleceń.")
        return

    table = Table("ID", "Symbol", "Side", "Type", "Qty", "Price", "Stop Price", "Status")
    for o in open_orders:
        table.add_row(
            o['client_order_id'],
            o['symbol'],
            o['side'],
            o['type'],
            str(o['quantity']),
            str(o.get('price') or '-'),
            str(o.get('stop_price') or '-'),
            o['status'],
        )
    print(table)


@app.command("fills")
def fills():
    # This functionality would require querying the database directly,
    # as the enhanced broker doesn't keep fills in memory.
    # For now, let's show positions as a proxy.
    print("[yellow]Listing closed positions as a proxy for fills:[/yellow]")
    # A more complete implementation would be needed here.
    pos = broker.get_open_positions() # A proper get_fills method should be implemented
    if not pos:
        typer.echo("Brak danych.")
    else:
        print(pos)


@app.command("close-all")
def close_all():
    open_positions = broker.get_open_positions()
    if not open_positions:
        typer.echo("Brak otwartych pozycji do zamknięcia.")
        return
        
    count = 0
    for p in open_positions:
        result = broker.close_position(p['symbol'])
        if result.get("success"):
            count += 1
    
    typer.echo(f"Zamknięto {count} pozycji.")


def main(argv: Optional[list[str]] = None) -> int:
    try:
        app()
        return 0
    except SystemExit as e:  # Typer may raise SystemExit
        return int(e.code) if isinstance(e.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())


