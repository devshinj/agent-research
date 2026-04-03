# Risk Management Rules

## Position Limits
- Max 25% of total equity per position
- Max 4 open positions simultaneously
- No duplicate buys (same coin)
- Minimum order: 5,000 KRW (Upbit limit)

## Stop Loss / Take Profit
- Stop loss: -2% from entry
- Take profit: +5% from entry
- Trailing stop: -1.5% from highest price since entry

## Daily Limits
- Max daily loss: 5% of initial balance
- Max daily trades: 50

## Circuit Breaker
- Trigger: 5 consecutive losses
- Action: Halt all BUY signals for 60 minutes
- Reset: After cooldown OR after a winning trade

## Risk Check Flow (5-step gate)
1. Circuit breaker check
2. Daily limit check
3. Position limit check
4. Duplicate position check
5. Position sizing + minimum order check
