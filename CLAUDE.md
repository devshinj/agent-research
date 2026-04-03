# CLAUDE.md

## Project
Upbit-based crypto paper trading system with ML strategy.

## Commands
- `uv sync` — install dependencies
- `uv run pytest` — run all tests
- `uv run pytest tests/structural/` — structural tests only
- `uv run ruff check src/` — lint
- `uv run mypy src/` — type check

## Conventions
- Python 3.12+, strict mypy, ruff formatting
- 6-layer architecture: types → config → repository → service → runtime → ui
- Financial math uses Decimal, never float
- All orders pass through RiskManager.approve() before PaperEngine
- Single FeatureBuilder class for both training and prediction
