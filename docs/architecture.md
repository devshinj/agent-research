# Architecture

## 6-Layer Modular Monolith

```
Layer 0: src/types/      — Pure domain models and enums. No dependencies.
Layer 1: src/config/     — Settings loader. Depends on: types
Layer 2: src/repository/ — Database access. Depends on: types, config
Layer 3: src/service/    — Business logic. Depends on: types, config, repository
Layer 4: src/runtime/    — Orchestration. Depends on: types, config, repository, service
Layer 5: src/ui/         — Presentation. Depends on: all lower layers
```

## Event Flow

```
collector →[NewCandleEvent]→ screener →[ScreenedCoinsEvent]→ predictor
predictor →[SignalEvent]→ risk_manager → paper_engine
paper_engine →[TradeEvent]→ portfolio → dashboard (WebSocket)
```

## Key Invariants
- Layer dependencies flow downward only (enforced by structural tests)
- Financial calculations use Decimal (enforced by structural tests)
- All orders pass through RiskManager.approve() before execution
- Single FeatureBuilder for train and predict (prevents train-serve skew)
