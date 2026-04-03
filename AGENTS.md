# Crypto Paper Trader — Agent Guide

## Architecture
6-layer modular monolith. See docs/architecture.md
Layer rule: types -> config -> repository -> service -> runtime -> ui
NEVER import from a higher layer. tests/structural/ enforces this.

## Key Directories
- src/types/      — Pure models, no deps
- src/config/     — Settings loader (Pydantic)
- src/repository/ — DB access (SQLite)
- src/service/    — Business logic (collector, screener, ML, trading)
- src/runtime/    — Event bus, scheduler, app lifecycle
- src/ui/         — FastAPI + React dashboard

## Rules
- Financial calculations: Decimal only, never float
- All orders go through RiskManager.approve() first
- Feature pipeline: single FeatureBuilder for train AND predict
- Config changes: update settings.yaml AND docs/

## Testing
- pre-commit: ruff + mypy + structural tests
- CI: structural -> unit -> integration (3 stages)

## Docs (source of truth)
- docs/architecture.md
- docs/layer-rules.md
- docs/ml/feature-catalog.md
- docs/trading/risk-rules.md
- docs/api/dashboard-endpoints.md
