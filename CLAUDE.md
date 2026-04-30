# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Config-driven framework for mock MCP servers. Each "profile" is an OpenAPI 3.1 YAML file under `configs/` with `x-mock-*` extensions describing the mock behavior. The CLI (`uv run mock-mcp --config <name>`) loads a profile, builds a FastAPI app, and exposes MCP at `/mcp`.

Used to swap out slow/flaky real tools during agent evaluation runs.

## Commands

```bash
uv sync                                       # install deps
uv run mock-mcp --config monthly-report       # run bundled profile
uv run mock-mcp --config <name> --port 9000   # override port
```

There are no tests, lint config, or CI in this repo.

## Architecture — load-bearing invariants

1. **OAS is the source of truth for the MCP tool schema.** `app/mcp_server.py:build_tools` walks the authored OAS dict directly to produce the MCP tool list — it does NOT introspect FastAPI routes. This is why we can keep dynamically-registered shim handlers simple (string-typed query params, no `response_model`) without losing schema fidelity. If you need MCP-visible behavior to change, change the YAML, not the FastAPI route registration.

2. **Determinism via `seed_from`.** `app/mock/engine.py` SHA-256-hashes the resolved request value to seed both Python's RNG and Faker. SHA-256 (not Python's `hash()`) is deliberate — survives `PYTHONHASHSEED` randomization across processes. Don't introduce other RNG sources or unseeded `random` calls in the engine. The one intentional non-deterministic recipe is `{now: true}`.

3. **`x-mock-static` XOR `x-mock-dynamic` per operation.** `_validate` in `app/loader.py` enforces this. Adding new mock-data modes? Update both the validator and `_register_route`'s dispatch.

## Extension points

- **New recipe verb** (e.g. `{uuid: ...}`): add a handler in `app/mock/recipes.py`, register it in `_HANDLERS`, add `RECIPE_KEYS` entry, document in README's "Recipe catalog".
- **New derived op** (e.g. `{abs: ...}`): add to `_OPS` in `app/mock/derived.py`, add to `EXPR_KEYS`, document in README's "Derived DSL" table.
- **New custom validator** (for OAS-inexpressible rules like "past month"): add a function to `VALIDATORS` in `app/validators.py`, document in README.
- **New top-level `x-mock-*` extension**: read it in `build_app` in `app/loader.py`, propagate to wherever consumes it. Strip via `_strip_x_mock` so it doesn't leak into `/openapi.json` or the MCP tool list.

## Testing changes

Acceptance bar for new features: the bundled `configs/monthly-report.yaml` profile must continue to produce a response where:
- `total_brands == sum(brands_by_platform.values())`
- `YES + NO + DONE == total_brands`
- Same `report_month` → same response (modulo `generated_at`).

Quick check:

```bash
uv run mock-mcp --config monthly-report --port 8001 &
curl -sS -H "Authorization: Bearer mock-test-token" \
  "http://localhost:8001/reports/generate?report_month=2025-06" | jq .
```

## YAML 1.1 footgun

PyYAML treats `yes`/`no`/`on`/`off` as booleans. The `monthly-report` config quotes `"YES"`/`"NO"`/`"DONE"` for this reason. Document this in any new profile that uses similar keys.
