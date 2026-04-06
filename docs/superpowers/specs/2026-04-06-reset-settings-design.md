# Reset & Settings Adjustment Feature

## Summary

Add the ability to reset trading data (balance, orders, positions, risk state) while preserving ML models and candle data, and allow users to adjust all configuration values through the Settings UI before restarting the system.

## User Flow

1. User clicks "초기화 & 재설정" button in Settings page
2. System pauses automatically (`POST /api/control/pause`)
3. Settings panel switches to edit mode — all fields become editable inputs pre-filled with current YAML values
4. User adjusts desired values
5. User clicks "적용 & 시작"
6. Confirmation modal: "잔고와 거래내역이 모두 초기화됩니다. 진행하시겠습니까?"
7. On confirm → `POST /api/control/reset` with new settings
8. Backend: truncate trading tables, write config.yaml, reinitialize in-memory state, unpause
9. UI returns to read-only mode with status RUNNING

## Backend

### New API Endpoints

#### `GET /api/config`

Returns current `config/settings.yaml` as JSON. Frontend uses this to populate form defaults.

Response: flat JSON matching YAML structure (paper_trading, risk, screening, strategy, collector, data sections).

#### `POST /api/control/reset`

Request body: full settings JSON (same structure as GET /api/config response).

Processing order:
1. `app.paused = True`
2. DB truncate: `orders`, `positions`, `account_state`, `daily_summary`, `risk_state`
3. Overwrite `config/settings.yaml` with new values
4. Reload `App.settings` from updated YAML
5. Reinitialize dependent services: `RiskManager`, `PaperEngine`, `PortfolioManager`, `Screener`
6. Reset `App.account` to new `PaperAccount(initial_balance=new_val, cash_balance=new_val)`
7. Reset `RiskManager` internal state (consecutive_losses, cooldown, daily counters)
8. `app.paused = False`

**Preserved data**: `candles` table, `screening_log` table, `data/models/` directory.

### Database Changes

Add `reset_trading_data()` method to `Database` class:

```python
async def reset_trading_data(self) -> None:
    await self.conn.executescript("""
        DELETE FROM orders;
        DELETE FROM positions;
        DELETE FROM account_state;
        DELETE FROM daily_summary;
        DELETE FROM risk_state;
    """)
    await self.conn.commit()
```

### App Changes

Add `reset(new_settings: Settings)` method to `App` class:

```python
async def reset(self, new_settings: Settings) -> None:
    self.paused = True
    await self.db.reset_trading_data()
    self.settings = new_settings
    # Reinitialize services with new config
    self.risk_manager = RiskManager(new_settings.risk, new_settings.paper_trading)
    self.paper_engine = PaperEngine(new_settings.paper_trading)
    self.portfolio_manager = PortfolioManager(new_settings.risk)
    self.screener = Screener(new_settings.screening)
    # Reset account
    self.account = PaperAccount(
        initial_balance=new_settings.paper_trading.initial_balance,
        cash_balance=new_settings.paper_trading.initial_balance,
    )
    self.paused = False
```

### YAML Write

Write settings back to `config/settings.yaml` using `yaml.safe_dump` preserving comments is not feasible with PyYAML — accept that comments will be lost on reset. Write with Korean-friendly structure comments as section headers.

## Frontend

### Settings.tsx Changes

**State additions**:
- `editMode: boolean` — toggles between read-only and edit mode
- `formValues: ConfigValues` — holds editable form state
- `showConfirmModal: boolean` — confirmation dialog visibility

**Read-only mode** (default): identical to current UI, but with "초기화 & 재설정" button added to panel header.

**Edit mode**: each setting row becomes an `<input type="number">` or `<input type="text">` (for always_include). Grouped by section as currently displayed.

**Confirmation modal**: simple overlay with warning text and "확인" / "취소" buttons.

**Config loading**: on mount, `GET /api/config` to populate formValues.

### Editable Fields

| Section | Field | Type | Unit |
|---------|-------|------|------|
| paper_trading | initial_balance | number | KRW |
| paper_trading | max_position_pct | number | ratio (0-1) |
| paper_trading | max_open_positions | number | count |
| paper_trading | fee_rate | number | ratio |
| paper_trading | slippage_rate | number | ratio |
| paper_trading | min_order_krw | number | KRW |
| risk | stop_loss_pct | number | ratio |
| risk | take_profit_pct | number | ratio |
| risk | trailing_stop_pct | number | ratio |
| risk | max_daily_loss_pct | number | ratio |
| risk | max_daily_trades | number | count |
| risk | consecutive_loss_limit | number | count |
| risk | cooldown_minutes | number | minutes |
| screening | min_volume_krw | number | KRW |
| screening | min_volatility_pct | number | % |
| screening | max_volatility_pct | number | % |
| screening | max_coins | number | count |
| screening | refresh_interval_min | number | minutes |
| screening | always_include | text | comma-separated |
| strategy | lookahead_minutes | number | minutes |
| strategy | threshold_pct | number | ratio |
| strategy | retrain_interval_hours | number | hours |
| strategy | min_confidence | number | ratio |
| collector | candle_timeframe | number | minutes |
| collector | max_candles_per_market | number | count |
| collector | market_refresh_interval_min | number | minutes |
| data | db_path | text | path |
| data | model_dir | text | path |
| data | stale_candle_days | number | days |
| data | stale_model_days | number | days |
| data | stale_order_days | number | days |

## File Changes

| Layer | File | Change |
|-------|------|--------|
| repository | `src/repository/database.py` | Add `reset_trading_data()` |
| runtime | `src/runtime/app.py` | Add `reset()` method |
| ui/api | `src/ui/api/routes/control.py` | Add `POST /reset`, `GET /config` |
| ui/frontend | `src/ui/frontend/src/pages/Settings.tsx` | Edit mode form + confirmation modal |
