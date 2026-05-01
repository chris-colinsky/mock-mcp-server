# Config reference

A profile is a single OpenAPI 3.1 document with framework extensions sprinkled in. Standard OAS describes the API surface; `x-mock-*` extensions describe the mock behavior.

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

## Top-level extensions

### `x-mock-port` — default bind port

```yaml
x-mock-port: 8001
```

Overridden by the CLI's `--port` flag.

### `x-mock-auth` — bearer auth

```yaml
x-mock-auth:
  type: bearer
  token_env: BEARER_TOKEN     # env var that overrides the configured token
  default: mock-test-token    # used when token_env is unset
```

When present, every authored route requires `Authorization: Bearer <token>`. Token resolution is `os.environ[token_env]` if set, else `default`. The built-in `/`, `/health`, `/mcp`, and `/openapi.json` routes are not auth-protected.

Omit the block entirely to leave the server fully open (the bundled `inventory-briefing` profile demonstrates this).

For full coverage — token resolution rules, MCP header forwarding, the `security:` / `securitySchemes` documentary-vs-enforced distinction, common gotchas — see [auth.md](auth.md).

### `x-mock-mcp` — MCP server settings

```yaml
x-mock-mcp:
  mount_path: /mcp                      # default: /mcp
  exclude_tags: [root, health]          # operations with these tags become regular HTTP routes but not MCP tools
  forward_headers: [authorization]      # which headers to forward from MCP client → dispatched HTTP call
```

All keys optional; defaults shown above are sensible.

## Per-operation extensions

Every operation must define exactly one of `x-mock-static` or `x-mock-dynamic`. The loader rejects configs that violate this with a clear error at startup.

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
  seed_from: query.report_month     # optional — see Determinism below
  response: <recipe tree>           # the response shape, with recipes at leaves
  derived: <list of derived ops>    # post-walk fixups (sums, products, refs)
```

The keys:

- `seed_from` — *optional*. Path to a request value (e.g. `query.id`, `path.user_id`) used to seed both the RNG and Faker. Omit for fresh randomness on every call.
- `response` — the response body shape. Recipes at leaves; see [recipes.md](recipes.md).
- `derived` — *optional* list of post-walk transformations. See [derived.md](derived.md).

**Determinism (`seed_from`)** — The resolved request value is SHA-256-hashed (so determinism survives `PYTHONHASHSEED` randomization across processes) and used to seed both Python's `random` and Faker. Same input → same output, across machines and processes.

### `x-mock-validate` — extra request validators

For rules you can't express in standard OAS keywords. See [validation.md](validation.md) for OAS keywords first (those handle most cases without needing this).

```yaml
x-mock-validate:
  - field: report_month
    type: past_month_utc
```

## Built-in routes (auto-mounted)

Three routes are added automatically by the loader — they're framework concerns, not part of your authored contract:

| Route        | Method | Purpose                                  |
|--------------|--------|------------------------------------------|
| `/`          | GET    | Welcome message + pointers to docs/health |
| `/health`    | GET    | Healthcheck for orchestrators (Fly, K8s, …) |
| `/mcp`       | POST/GET/DELETE | MCP streamable-HTTP endpoint        |

`/` and `/health` are tagged so they're excluded from the MCP tool list by default (`x-mock-mcp.exclude_tags`).
