# Example: monthly-report

[`configs/monthly-report.yaml`](../../configs/monthly-report.yaml)

This profile exercises every framework feature: dynamic recipes, derived DSL, sum/delta invariants, custom validators (`past_month_utc`), bearer auth, and seeded determinism. It mocks a Sales & Operations Planning–style report endpoint that the original mock-mcp-server was built to replace.

## Endpoint

`GET /reports/generate?report_month=YYYY-MM&use_preview_db=bool`

- `report_month` (required, string, `YYYY-MM`): which month to report on.
- `use_preview_db` (optional, boolean, default false): pick `preview` vs `prod` environment in the response.

## Run + hit it

```bash
uv run mock-mcp --config monthly-report
curl -H "Authorization: Bearer mock-test-token" \
  "http://localhost:8001/reports/generate?report_month=2025-06"
```

## Response generator, step by step

The dynamic generator walks like this (matching the order RNG draws happen):

1. **`seed_from: query.report_month`** — same month always produces the same output. SHA-256 of the value seeds both `random` and Faker.
2. **Brand counts per platform** — four `random_int` draws (`Impact`, `Rakuten`, `CJ`, `Howl`) within realistic ranges. Determines the eventual total.
3. **`total_platform_earnings`** — uniform float in [200000, 500000], rounded to 2 dp.
4. **`environment`** — pulled from the `use_preview_db` query param via a `from`+`map` combo.
5. **`output_file_path`** — built via `template`, with `year` and `month` split out of `report_month` using `from`'s `split` option.

Then `derived:` runs in declared order:

6. **`total_brands`** = sum of platform counts. `{sum_of: /summary_stats/brands_by_platform}`. No RNG draw — pure aggregation.
7. **`total_link_adjusted_spend`** = `earnings * (1 - U(0.001, 0.01))`, rounded. The random draw for `delta_pct` happens *inside* this expression, so it's part of the deterministic stream.
8. **`total_link_delta`** = `earnings - adjusted_spend`, rounded. Uses `ref` to look up both already-written values.
9. **`DONE` count** — `random_int(5, total_brands * 0.2)` — random within bounds derived from `total_brands`.
10. **`YES` count** — `random_int(total_brands * 0.3, total_brands * 0.6)`.
11. **`NO` count** — `total_brands - DONE - YES` (the remainder, ensures invariant).

Three invariants hold for every response:

- `total_brands == sum(brands_by_platform.values())`
- `total_link_delta == round(total_platform_earnings - total_link_adjusted_spend, 2)`
- `YES + NO + DONE == total_brands`

`tests/test_e2e.py` checks all three for every response shape.

## Validation

Two-stage:

- **Stage 1** — OAS `pattern: '^\d{4}-\d{2}$'` on `report_month`. Catches malformed shapes (`"garbage"`, `"2025-1"`).
- **Stage 2** — `x-mock-validate.past_month_utc` (built-in custom validator). Catches calendar invalidity (`"2025-13"`) and the past-month rule (current month and future are not allowed).

Both fail with 422 and a structured error body. See [validation.md](../validation.md) for the framework's validation tiers.

## Auth

`x-mock-auth.type: bearer` with `token_env: BEARER_TOKEN, default: mock-test-token`. Override the default token via env var when running:

```bash
BEARER_TOKEN=my-secret uv run mock-mcp --config monthly-report
```

## Why this profile is the smoke-test for the framework

Every feature gets exercised:

- ✅ Dynamic generator with `seed_from` for determinism
- ✅ Recipe leaves: `static`, `random_int`, `random_float` (with `round`), `from` (with `map` and `split`), `now`, `template`
- ✅ Derived ops: `ref`, `sum_of`, `mul`, `sub`, `round`, `to_int`
- ✅ Custom validator (`past_month_utc`)
- ✅ Bearer auth with env-var override
- ✅ `$ref` in OAS schemas (resolved into the MCP tool list)
- ✅ Cross-field invariants verified by tests

If you change the framework and break this profile, you've broken something real. CI runs the full e2e suite on every push.
