---
name: decimal-finance
description: Use Decimal (not float) for all financial calculations — prices, balances, fees, PnL, quantities, percentages applied to money. Use this skill whenever writing code in src/service/ or src/repository/ that deals with money, prices, order quantities, fee calculations, PnL, or risk thresholds. Even a single float in the financial path will silently corrupt calculations.
---

# Decimal Finance

All financial values in this project use `decimal.Decimal`. This is enforced by structural tests that scan for float literals in financial code.

## What Must Be Decimal

- Prices (entry, fill, current, high, low, open, close)
- Balances (cash, initial, ending)
- Quantities (order size, position size)
- Fees and slippage
- PnL (realized, unrealized)
- Percentages when applied to money (stop_loss_pct * price)
- Volume in KRW

## What Can Stay as float

- ML confidence scores (0.0–1.0) — these are probabilities, not money
- Feature values for ML input (returns, RSI, MACD, etc.)
- Timestamps (int preferred, but float acceptable from APIs)

## Patterns

**Creating Decimal from API data (which returns float):**
```python
price = Decimal(str(api_response["trade_price"]))
```
Never do `Decimal(0.1)` — this captures the float imprecision. Always `Decimal("0.1")` or `Decimal(str(value))`.

**Arithmetic:**
```python
fee = price * quantity * settings.risk.fee_rate  # all Decimal, result is Decimal
```

**Comparison:**
```python
if unrealized_pnl <= -entry_price * stop_loss_pct:  # Decimal comparison
```

## Verification

Run: `uv run pytest tests/structural/test_decimal_enforcement.py -x -q`

This test scans src/ for float literals in financial code paths and fails if any are found.
