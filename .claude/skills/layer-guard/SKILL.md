---
name: layer-guard
description: Enforces the 6-layer dependency rule (types -> config -> repository -> service -> runtime -> ui) when creating or modifying Python files in src/. Use this skill whenever you are about to write an import statement in any src/ module, create a new file in src/, or move code between layers. Also use when reviewing code that touches multiple layers. Even a single misplaced import breaks the architecture — this skill prevents that.
---

# Layer Guard

This project uses a strict 6-layer architecture. Each layer can only import from layers below it, never above or sideways at the same level (except within the same layer).

## Layer Map

```
Layer 0: src/types/      — imports: nothing from src/
Layer 1: src/config/     — imports: src/types only
Layer 2: src/repository/ — imports: src/types, src/config
Layer 3: src/service/    — imports: src/types, src/config, src/repository
Layer 4: src/runtime/    — imports: src/types, src/config, src/repository, src/service
Layer 5: src/ui/         — imports: all lower layers
```

## Before Writing Any Import

1. Identify which layer the **current file** is in (by its directory under src/)
2. Identify which layer the **target module** is in
3. If target layer number >= current layer number, STOP. This import is illegal.
4. If it's a stdlib or third-party import, it's always fine.

## Common Violations to Watch For

- `src/service/` importing from `src/runtime/` (layer 3 importing layer 4)
- `src/repository/` importing from `src/service/` (layer 2 importing layer 3)
- `src/config/` importing from anything other than `src/types/`
- `src/types/` importing from any `src/` module

## When You Need Cross-Layer Communication

If a lower layer needs to react to something in a higher layer, use the event bus pattern:
- The higher layer publishes an event (via `src/runtime/event_bus.py`)
- The lower layer defines the event type in `src/types/events.py`
- The runtime layer wires them together

## Verification

After writing code, run: `uv run pytest tests/structural/test_layer_deps.py -x -q`

This is a hard gate — if it fails, fix the import before proceeding.
