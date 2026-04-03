# Layer Dependency Rules

## Allowed Dependencies

| Layer | Can Import From |
|-------|----------------|
| L0 types | (nothing) |
| L1 config | types |
| L2 repository | types, config |
| L3 service | types, config, repository |
| L4 runtime | types, config, repository, service |
| L5 ui | types, config, repository, service, runtime |

## Enforcement
- `scripts/check_layers.py` — standalone checker
- `tests/structural/test_layer_deps.py` — pytest integration
- `.pre-commit-config.yaml` — pre-commit hook
- CI pipeline Stage 1 — blocks merge on violation
