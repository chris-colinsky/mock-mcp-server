# mock-mcp-server

A config-driven framework for standing up mock MCP (Model Context Protocol) servers — useful for agent evaluation harnesses (deepeval, custom eval loops) where the real tool calls are slow, flaky, or expensive.

You describe the API surface as **OpenAPI 3.1 + a few `x-mock-*` extensions** in a YAML file, drop it under `configs/`, and run it by name:

```bash
uv run mock-mcp --config monthly-report
```

The server speaks MCP at `/mcp` and serves the same tools as a regular HTTP API at the operation paths.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Quick start](#quick-start)
- [CLI](#cli)
- [Config file structure](#config-file-structure)
- [Top-level `x-mock-*` extensions](#top-level-x-mock--extensions)
- [Per-operation `x-mock-*` extensions](#per-operation-x-mock--extensions)
- [Recipe catalog (`x-mock-dynamic.response`)](#recipe-catalog-x-mock-dynamicresponse)
- [Derived DSL (`x-mock-dynamic.derived`)](#derived-dsl-x-mock-dynamicderived)
- [Built-in custom validators](#built-in-custom-validators)
- [Worked example: monthly-report](#worked-example-monthly-report)
- [Authoring strategies](#authoring-strategies)
- [Bootstrapping a config from a real app](#bootstrapping-a-config-from-a-real-app)
- [Adding a new profile (walkthrough)](#adding-a-new-profile-walkthrough)
- [Project layout](#project-layout)
- [Limitations](#limitations)

---

## Why this exists

Real production tools often call many backend services and take seconds per invocation. When an evaluation harness invokes the same tool hundreds of times, runs become impractical. This framework gives you a **drop-in mock** that:

- Returns realistic, **deterministic** synthetic data for the same input (seeded RNG keyed off a request param).
- Speaks **MCP** at `/mcp` so eval harnesses can plug in without code changes.
- Emits the **same OpenAPI shape** as the real server, so the tool schema your agent sees is identical.
- Runs **instantly**, no external services touched.

Profiles are just YAML — no Python required to add a new mock.

---

## Quick start

```bash
# 1. install
uv sync

# 2. run the bundled monthly-report profile
uv run mock-mcp --config monthly-report

# 3. hit it
curl -H "Authorization: Bearer mock-test-token" \
  "http://localhost:8001/reports/generate?report_month=2025-06"
```

Output (abridged):

```json
{
  "success": true,
  "message": "Monthly report generated successfully",
  "report_month": "2025-06",
  "generated_at": "2026-04-30T21:30:00.000000+00:00",
  "output_file_path": "s3://mock-bucket/.../year=2025/month=06/monthly_summary_report.csv",
  "summary_stats": {
    "brands_by_platform": {"Impact": 26, "Rakuten": 37, "CJ": 25, "Howl": 16},
    "total_platform_earnings": 362641.55,
    "environment": "prod",
    "total_brands": 104,
    "total_link_adjusted_spend": 359826.36,
    "total_link_delta": 2815.19,
    "draft_invoice_summary": {"YES": 57, "NO": 37, "DONE": 10}
  }
}
```

The MCP endpoint is at `http://localhost:8001/mcp`. Standard FastAPI docs at `/docs`, `/redoc`, `/openapi.json`.

---

## CLI

```
mock-mcp --config <profile> [--port N] [--host HOST] [--reload]
```

| flag | required | default | notes |
|---|---|---|---|
| `--config` | yes | — | Profile name. Resolved as `configs/<name>.yaml` (or `.yml`). No default — missing/invalid configs error out with exit code 2. |
| `--port` | no | from config (`x-mock-port`) | Bind port. Overrides the config. |
| `--host` | no | `0.0.0.0` | Bind host. |
| `--reload` | no | off | Uvicorn auto-reload (dev only). |

Examples:

```bash
mock-mcp --config monthly-report
mock-mcp --config monthly-report --port 9001
mock-mcp --config some-other-profile --reload
```

If `configs/foo.yaml` doesn't exist:

```
$ mock-mcp --config foo
error: config profile not found: 'foo' (looked in /…/configs for foo.yaml or foo.yml)
$ echo $?
2
```

---

## Config file structure

Every profile is a single OpenAPI 3.1 document with framework extensions sprinkled in. Standard OAS describes the API surface; `x-mock-*` extensions describe the mock behavior.

```yaml
openapi: 3.1.0
info:
  title: My Mock API
  version: 1.0.0

# --- framework-level config ---
x-mock-port: 8001
x-mock-auth:
  type: bearer
  token_env: MY_TOKEN
  default: dev-token
x-mock-mcp:
  exclude_tags: [root, health]

# --- API surface (standard OAS) ---
paths:
  /widgets/{id}:
    get:
      operationId: get_widget
      tags: [widgets]
      parameters:
        - { name: id, in: path, required: true, schema: { type: string } }

      # --- per-operation mock behavior ---
      x-mock-dynamic:
        seed_from: path.id
        response:
          id:    { from: path.id }
          name:  { faker: company.name }
          price: { random_float: { range: [10, 500], round: 2 } }

      responses:
        '200':
          description: OK
          content:
            application/json: { schema: { $ref: '#/components/schemas/Widget' } }

components:
  schemas:
    Widget:
      type: object
      required: [id, name, price]
      properties:
        id:    { type: string }
        name:  { type: string }
        price: { type: number }
```

That's the entire shape. Standard OAS authors the contract; `x-mock-*` authors the behavior.

---

## Top-level `x-mock-*` extensions

### `x-mock-port` — bind port

```yaml
x-mock-port: 8001
```

Used as the default bind port. Overridden by `--port`.

### `x-mock-auth` — bearer auth

```yaml
x-mock-auth:
  type: bearer
  token_env: BEARER_TOKEN     # env var that overrides the configured token
  default: mock-test-token    # used when token_env is unset
```

When present, every authored route requires a valid `Authorization: Bearer <token>` header. The expected token is `os.environ[token_env]` if set, else `default`. Built-in `/`, `/health`, and `/mcp` routes are **not** auth-protected (they're built-ins for the framework, not part of the authored contract). Forwarded headers from MCP `tools/call` requests are used to authenticate dispatched calls — so configure your MCP client to send `Authorization` and it'll pass through.

If you omit `x-mock-auth`, the server is unauthenticated.

### `x-mock-mcp` — MCP server settings

```yaml
x-mock-mcp:
  mount_path: /mcp                      # default: /mcp
  exclude_tags: [root, health]          # operations with these tags become regular HTTP routes but not MCP tools
  forward_headers: [authorization]      # which headers to forward from MCP client → dispatched HTTP call
```

All keys optional; defaults shown above are sensible.

---

## Per-operation `x-mock-*` extensions

### `x-mock-static` — literal response

Returns the value verbatim. Use for endpoints where the response shape is fixed and you don't need synthesis.

```yaml
paths:
  /version:
    get:
      operationId: get_version
      x-mock-static:
        version: "1.0.0"
        commit: "deadbeef"
        build_time: "2024-01-15T00:00:00Z"
      responses:
        '200': { description: OK, content: { application/json: { schema: { type: object } } } }
```

### `x-mock-dynamic` — generated response

```yaml
x-mock-dynamic:
  seed_from: query.report_month     # optional — see "Determinism" below
  response: <recipe tree>           # the response shape, with recipes at leaves
  derived: <list of derived ops>    # post-walk fixups (sums, products, refs)
```

You must define **exactly one** of `x-mock-static` or `x-mock-dynamic` per operation. The loader rejects configs that violate this.

#### Determinism (`seed_from`)

`seed_from: <request-path>` ensures the same input always produces the same output. The path is dotted (`query.X`, `path.Y`); the resolved value is SHA-256-hashed (so determinism survives `PYTHONHASHSEED` randomization across processes) and used to seed both the RNG and Faker. Omit `seed_from` if you want fresh data per request.

### `x-mock-validate` — extra request validators

Standard OAS keywords (`pattern`, `enum`, `minLength`, `minimum`, etc.) cover most validation needs. Use `x-mock-validate` only for rules you can't express in plain OAS:

```yaml
x-mock-validate:
  - field: report_month
    type: past_month_utc
```

See [Built-in custom validators](#built-in-custom-validators) for the validator catalog.

---

## Recipe catalog (`x-mock-dynamic.response`)

A **recipe** is a one-key dict whose key is one of the verbs below. Anywhere a recipe appears in the `response` tree, it's evaluated; everything else is left alone (literals pass through). Recipes can sit anywhere — top level, inside dicts, inside lists.

The walk is **top-down, declared order**. RNG draws happen in that order, which matters if you care about reproducing a specific sequence.

### `static` — literal value

```yaml
success: { static: true }
message: { static: "Generated successfully" }
empty:   { static: [] }
```

### `random_int: [low, high]` — uniform integer (inclusive)

```yaml
total_items: { random_int: [10, 100] }
```

Bounds may be expressions, evaluated via the [derived DSL](#derived-dsl-x-mock-dynamicderived):

```yaml
done_count:
  random_int:
    - 5
    - { to_int: { mul: [{ ref: /summary_stats/total_brands }, 0.2] } }
```

### `random_float` — uniform float

Two forms:

```yaml
# raw uniform
delta_pct: { random_float: [0.001, 0.01] }

# uniform + rounding
total_earnings:
  random_float:
    range: [200000, 500000]
    round: 2
```

### `random_choice: [...]` — pick one

```yaml
status:   { random_choice: [pending, complete, errored] }
priority: { random_choice: [1, 2, 3, 5, 8] }
```

### `faker` — call a [Faker](https://faker.readthedocs.io/) provider

```yaml
# short form: provider name
name:       { faker: company.name }
email:      { faker: email }
ip_address: { faker: ipv4 }

# long form: with args/kwargs
big_number:
  faker:
    provider: pyint
    kwargs:  { min_value: 1000, max_value: 999999 }
```

When `seed_from` is set, Faker is seeded with the same hash so its output is deterministic.

### `from` — pull a value from the request

Pull request fields into the response:

```yaml
# short form
report_month: { from: query.report_month }

# long form with map
environment:
  from:
    path: query.use_preview_db
    map: { true: preview, false: prod }

# long form with slicing (works on string values)
year_part:
  from: { path: query.report_month, slice: [0, 4] }    # "2025-06" → "2025"

# long form with split-and-index
month_part:
  from: { path: query.report_month, split: '-', index: 1 }   # "2025-06" → "06"
```

Paths: `query.<name>`, `path.<name>`. Combine `slice`/`split` with `map` to transform-then-map.

### `now` — current ISO-8601 UTC timestamp

The one intentional non-deterministic recipe.

```yaml
generated_at: { now: true }
```

### `template` — Python `str.format` interpolation

```yaml
output_file_path:
  template:
    format: "s3://bucket/year={year}/month={month}/data.csv"
    vars:
      year:  { from: { path: query.report_month, split: '-', index: 0 } }
      month: { from: { path: query.report_month, split: '-', index: 1 } }
```

Recipes inside `vars` are evaluated first; the resolved values are then substituted into `format`.

---

## Derived DSL (`x-mock-dynamic.derived`)

Use `derived:` for cross-field invariants — anything that needs to read other generated values. Each entry is `{path: <json-pointer>, value: <expression>}` (or `{delete: <json-pointer>}`). Entries are applied **in order**, so later entries can reference values written by earlier ones.

Recipe verbs (`random_int`, `from`, `faker`, …) are also valid expressions, so you can mix RNG draws with computed expressions naturally.

### Operators

| op | example | result |
|---|---|---|
| `ref` | `{ ref: /summary_stats/total }` | Look up a value by JSON Pointer. |
| `sum` | `{ sum: [1, 2, { ref: /a }] }` | Sum of arguments. |
| `sum_of` | `{ sum_of: /summary_stats/by_platform }` | Sum of all values in a dict or list. |
| `sub` | `{ sub: [10, 3, 1] }` → 6 | Subtract subsequent args from the first. |
| `mul` | `{ mul: [{ ref: /price }, 1.08] }` | Product. |
| `div` | `{ div: [{ ref: /total }, 4] }` | Division (exactly two args). |
| `round` | `{ round: { value: <expr>, digits: 2 } }` | Round. |
| `to_int` | `{ to_int: { mul: [{ ref: /n }, 0.5] } }` | Coerce to int. |
| `min` / `max` | `{ min: [{ ref: /a }, 100] }` | Min/max of evaluated args. |

### JSON Pointer paths

Standard RFC 6901: `/foo/bar`, `/list/0/key`. Escape `/` with `~1`, `~` with `~0`.

### Patterns

**Sum invariant** (computed total = sum of parts):

```yaml
response:
  counts:
    a: { random_int: [10, 50] }
    b: { random_int: [10, 50] }
    c: { random_int: [10, 50] }
  total: { static: 0 }     # placeholder

derived:
  - path: /total
    value: { sum_of: /counts }
```

**Derived ratio + remainder**:

```yaml
derived:
  - path: /adjusted
    value:
      round:
        digits: 2
        value:
          mul:
            - { ref: /raw }
            - { sub: [1, { random_float: [0.01, 0.05] }] }
  - path: /delta
    value:
      sub:
        - { ref: /raw }
        - { ref: /adjusted }
```

**Bounded random with cross-field reference**:

```yaml
- path: /done_count
  value:
    random_int:
      - 5
      - { to_int: { mul: [{ ref: /total }, 0.2] } }
```

**Cleanup with `delete`**:

```yaml
- delete: /scratch     # remove a field used for intermediate results
```

---

## Built-in custom validators

Reference these from `x-mock-validate`. Add new validators in `app/validators.py`.

| name | rule |
|---|---|
| `past_month_utc` | Value must parse as `YYYY-MM` and be strictly before the current UTC month. |

```yaml
x-mock-validate:
  - field: report_month
    type: past_month_utc
    message: "optional override message"
```

The framework prefers the validator's own message; `message:` is a fallback for cases where the validator raises a generic error.

---

## Worked example: monthly-report

The bundled `configs/monthly-report.yaml` exercises every framework feature. Walking through the dynamic generator:

1. **`seed_from: query.report_month`** — same month always produces the same output.
2. **Brand counts per platform** drawn from realistic ranges.
3. **`total_brands`** = sum of platform counts (derived, no RNG draw).
4. **`total_platform_earnings`** = uniform float in [200000, 500000], rounded to 2 dp.
5. **`total_link_adjusted_spend`** = `earnings * (1 - U(0.001, 0.01))`, rounded.
6. **`total_link_delta`** = `earnings - adjusted_spend`, rounded.
7. **`draft_invoice_summary`** counts (`DONE`, `YES`, `NO`) — random within bounds derived from `total_brands`, with `NO` as the remainder so the trio sums to `total_brands`.
8. **`output_file_path`** built via `template` with year/month split out of `report_month`.

Open the file alongside this README; every block has a comment explaining what it's doing.

---

## Authoring strategies

### Static vs. dynamic — when to use which

| Use **`x-mock-static`** when… | Use **`x-mock-dynamic`** when… |
|---|---|
| The response is a fixed fixture. | Numbers depend on the request. |
| Cross-field invariants are too complex to express as derived ops. | You want different output per `seed_from` value. |
| You're stubbing an endpoint while developing the real one. | You want realistic-looking but synthetic data (Faker). |
| The mock is a known constant from a prod sample. | You want determinism (`seed_from`) without hand-curating responses. |

In practice: start static (paste a real response from prod), upgrade to dynamic when you need variation.

### Determinism

Set `seed_from` to a request field that's stable for the call (`query.id`, `query.report_month`, `path.user_id`). Same value → same output, across processes and machines (SHA-256 keyed). Omit `seed_from` if you want fresh randomness on every call.

`generated_at`-style "current time" fields use `{now: true}` — that's deliberately non-deterministic.

### Cross-field invariants

The order of operations matters. Inside `response:`, leaves are walked in declared order, so RNG draws happen in that order. `derived:` runs after the whole tree is built and entries are applied in declared order, so an entry can reference values produced by earlier entries. Plan your config like a sequence of writes:

1. What's drawn from RNG, and in what order?
2. Which fields are computed from those?
3. Anything that depends on a computed value goes later.

### YAML 1.1 footguns to remember

PyYAML defaults to YAML 1.1 semantics, which means **`yes`, `no`, `on`, `off`, `y`, `n`** become booleans. If your data uses these strings as keys (e.g. `YES`, `NO`, `DONE`), **quote them**:

```yaml
draft_invoice_summary:
  "YES":  { static: 0 }   # not YES (becomes true)
  "NO":   { static: 0 }   # not NO  (becomes false)
  "DONE": { static: 0 }
```

### Debugging tips

- Hit `/openapi.json` to see the schema the MCP client will see.
- Hit `/docs` for an interactive Swagger UI of all your routes.
- The CLI returns exit 2 on config errors, with the failing path/operation in the message — easy to integrate into CI checks.
- `--reload` watches the `app/` package; YAML config changes need a manual restart (uvicorn doesn't watch files outside the importable package).

---

## Bootstrapping a config from a real app

If you already have a FastAPI app, bootstrap your mock config from its OpenAPI export:

```bash
# from the real app's repo:
python -c "from app.main import app; import yaml, sys; \
  yaml.safe_dump(app.openapi(), sys.stdout, sort_keys=False)" \
  > /tmp/real-app-oas.yaml

# copy to this repo, rename, prune fields you don't need, then add:
#   x-mock-port, x-mock-auth, x-mock-mcp at root
#   x-mock-static or x-mock-dynamic per operation
```

Your mock now has byte-equivalent schemas to the real app — only the bodies need filling in.

---

## Adding a new profile (walkthrough)

To mock an endpoint `GET /widgets/{id}`:

1. **Create the file** `configs/widget.yaml`:

   ```yaml
   openapi: 3.1.0
   info:
     title: Widget API
     version: 1.0.0

   x-mock-port: 8002
   x-mock-auth:
     type: bearer
     token_env: WIDGET_TOKEN
     default: dev-widget-token

   paths:
     /widgets/{id}:
       get:
         operationId: get_widget
         tags: [widgets]
         parameters:
           - { name: id, in: path, required: true, schema: { type: string } }
         x-mock-dynamic:
           seed_from: path.id
           response:
             id:        { from: path.id }
             name:      { faker: company.name }
             sku:       { faker: { provider: pystr, kwargs: { min_chars: 8, max_chars: 8 } } }
             price:     { random_float: { range: [9.99, 499.99], round: 2 } }
             in_stock:  { random_choice: [true, false] }
             created_at: { now: true }
         responses:
           '200':
             description: OK
             content:
               application/json: { schema: { $ref: '#/components/schemas/Widget' } }

   components:
     schemas:
       Widget:
         type: object
         required: [id, name, sku, price, in_stock, created_at]
         properties:
           id:         { type: string }
           name:       { type: string }
           sku:        { type: string }
           price:      { type: number }
           in_stock:   { type: boolean }
           created_at: { type: string, format: date-time }
   ```

2. **Run it**:

   ```bash
   uv run mock-mcp --config widget
   ```

3. **Test it**:

   ```bash
   curl -H "Authorization: Bearer dev-widget-token" \
     "http://localhost:8002/widgets/abc-123"
   ```

   Same `id` → same response.

4. **(Optional) connect an MCP client to** `http://localhost:8002/mcp` and you'll see `get_widget` listed as a tool.

---

## Project layout

```
mock-mcp-server/
├── pyproject.toml
├── configs/
│   └── monthly-report.yaml      # bundled profile
└── app/
    ├── __main__.py              # CLI: `mock-mcp --config <name>`
    ├── loader.py                # OAS + x-mock-* → FastAPI app
    ├── mcp_server.py            # /mcp endpoint, OAS → MCP tools
    ├── auth.py                  # bearer auth from x-mock-auth
    ├── validators.py            # registry of custom request validators
    └── mock/
        ├── recipes.py           # leaf recipes (random_*, faker, from, …)
        ├── derived.py           # derived DSL (sum, ref, …)
        └── engine.py            # orchestrate seed → recipes → derived
```

---

## Limitations

- **Request body schemas** are accepted in OAS form but not deeply validated against `requestBody.content[*].schema`. Bodies are passed through to dispatched calls verbatim. Open issue if you need strict body validation.
- **Recipes are evaluated eagerly.** Lazy refs in nested constructs (e.g. random within random with bounds depending on each other) work via the derived DSL, but pure recipe trees evaluate top-down once.
- **No SSE transport for MCP.** Only the streamable HTTP transport is mounted at `/mcp`. Add it in `app/mcp_server.py:attach` if you need it.
- **`tools/call` returns the response body as `TextContent` (JSON string).** This matches what most MCP clients expect; structured responses (multiple content blocks, images) aren't synthesized.
