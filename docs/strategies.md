# Authoring strategies

Practical patterns for writing useful profiles.

## Static vs. dynamic — when to use which

| Use **`x-mock-static`** when…                                  | Use **`x-mock-dynamic`** when…                              |
|----------------------------------------------------------------|-------------------------------------------------------------|
| The response is a fixed fixture.                               | Numbers depend on the request.                              |
| Cross-field invariants are too complex to express as derived. | You want different output per `seed_from` value.            |
| You're stubbing an endpoint while developing the real one.    | You want realistic-looking but synthetic data (Faker).      |
| The mock is a known constant from a prod sample.              | You want determinism (`seed_from`) without hand-curating.   |

In practice: **start static** (paste a real response from prod), **upgrade to dynamic** when you need variation.

## Determinism

Set `seed_from` to a request field that's stable for the call (`query.id`, `query.report_month`, `path.user_id`). Same value → same output, across processes and machines (SHA-256 keyed).

Omit `seed_from` if you want fresh randomness on every call — useful when mocking endpoints whose real implementation is non-deterministic (LLM calls, time-of-day jitter, etc.).

`generated_at`-style "current time" fields use `{now: true}` — that's deliberately non-deterministic even when `seed_from` is set, so a deterministic mock can still emit a fresh-looking timestamp.

## Cross-field invariants

The order of operations matters. Inside `response:`, leaves are walked in declared order, so RNG draws happen in that order. `derived:` runs after the whole tree is built and entries are applied in declared order, so an entry can reference values produced by earlier entries.

Plan your config like a sequence of writes:

1. What's drawn from RNG, and in what order?
2. Which fields are computed from those?
3. Anything that depends on a computed value goes later.

See `configs/monthly-report.yaml` — the order of derived entries (compute total → compute adjusted → compute delta → compute DONE/YES/NO splits) is intentional and documented inline.

## YAML 1.1 footguns to remember

PyYAML defaults to YAML 1.1 semantics, which means **`yes`, `no`, `on`, `off`, `y`, `n`** become booleans. If your data uses these strings as keys (e.g. `YES`, `NO`, `DONE`), **quote them**:

```yaml
draft_invoice_summary:
  "YES":  { static: 0 }   # not YES (becomes true)
  "NO":   { static: 0 }   # not NO  (becomes false)
  "DONE": { static: 0 }
```

Other quirks:

- `1.0` parses as float, `1` as int.
- `null`, `~`, and an empty value all become `None`.
- Times with colons can parse weirdly: quote anything date/time-shaped if you want it as a string.

## Debugging tips

- **Hit `/openapi.json`** to see the schema the MCP client will see — this is what your agent reads to learn the tool surface.
- **Hit `/docs`** for an interactive Swagger UI of all your routes; click "Try it out" to invoke any endpoint.
- **The CLI returns exit 2** on config errors, with the failing path/operation in the error message — easy to integrate into CI checks.
- **`make validate-configs`** loads + builds every YAML profile in `configs/`. Catches typos in `x-mock-*` extensions that the JSON schema can't (e.g. invalid pointer references).
- **`--reload`** watches the `app/` package; YAML config changes need a manual restart (uvicorn doesn't watch files outside the importable package).
- **The dispatch log line** (`mcp dispatch generate_report -> "GET /reports/generate?…" 200 (32ms)`) appears in stdout for every MCP `tools/call`. Confirms which route a tool actually invoked.

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

## Adding a new profile

To mock an endpoint `GET /widgets/{id}`:

1. **Create the file** `configs/widget.yaml`:

   ```yaml
   # yaml-language-server: $schema=../schemas/mock-mcp-config.schema.json
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

2. **Validate it**:

   ```bash
   make validate-configs
   ```

3. **Run it**:

   ```bash
   uv run mock-mcp --config widget
   ```

4. **Test it**:

   ```bash
   curl -H "Authorization: Bearer dev-widget-token" \
     "http://localhost:8002/widgets/abc-123"
   ```

   Same `id` → same response.

5. **(Optional) connect an MCP client** to `http://localhost:8002/mcp` and you'll see `get_widget` listed as a tool. The fastest way to do this is [Forbin](pairing-with-forbin.md).
