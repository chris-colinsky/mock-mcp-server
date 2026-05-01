# Auth

mock-mcp-server supports **bearer-token authentication** on authored routes. Auth is opt-in per profile — omit the `x-mock-auth` block and the server is fully open.

## TL;DR

```yaml
# at the top of your profile YAML
x-mock-auth:
  type: bearer
  token_env: BEARER_TOKEN     # env var that overrides the default
  default: mock-test-token    # used when token_env is unset
```

That's it. Every authored route now requires `Authorization: Bearer <token>`.

## What's protected, what isn't

When `x-mock-auth` is set:

| Route                                  | Auth required? | Notes                                                  |
|----------------------------------------|----------------|--------------------------------------------------------|
| Anything declared in your `paths:`     | **yes**        | These are the routes you authored.                     |
| `/` (root welcome)                     | no             | Framework built-in, not in your contract.              |
| `/health`                              | no             | Same — orchestrators (Fly, K8s, …) need to probe it.   |
| `/mcp`                                 | no (transport) | The MCP transport itself is unauthenticated; auth is enforced when the transport dispatches a tool call back to your authored route. See [Auth flow through MCP](#auth-flow-through-mcp) below. |
| `/openapi.json`, `/docs`, `/redoc`     | no             | FastAPI built-ins.                                     |

When `x-mock-auth` is omitted: nothing is protected. The server is fully open. The bundled `inventory-briefing` profile uses this mode.

## Two places auth shows up in YAML — and only one matters

A common point of confusion: there are **two parallel ways auth declarations can appear** in a profile, and only one of them does anything.

### `x-mock-auth` — the framework reads this

This block (top-level, an `x-` extension) is what the framework actually enforces. It registers a FastAPI dependency that 401s requests without a valid bearer token.

### `security:` + `components.securitySchemes.*` — purely advisory

These are standard OAS declarations:

```yaml
paths:
  /widgets:
    get:
      security:
        - BearerAuth: []     # <-- documentary only

components:
  securitySchemes:
    BearerAuth:               # <-- documentary only
      type: http
      scheme: bearer
```

They show up in `/openapi.json` so MCP clients, Swagger UI, and anyone reading your spec know "this endpoint expects a bearer token." But **the framework never reads them.** Removing them doesn't disable auth; adding them doesn't enable it.

The `monthly-report` profile includes both `x-mock-auth` (which enforces) and `security:` / `securitySchemes` (for documentation parity with what a real production server would publish). The `inventory-briefing` profile includes neither — it's open.

## Token resolution

Order of precedence:

1. **`os.environ[token_env]`** if `token_env` is set and the env var is non-empty.
2. **`default`** otherwise.

If neither resolves to a value, profile loading fails with a clear error.

```yaml
x-mock-auth:
  type: bearer
  token_env: BEARER_TOKEN
  default: mock-test-token
```

```bash
# uses the default (mock-test-token)
uv run mock-mcp --config monthly-report

# override at runtime via env var
BEARER_TOKEN=staging-secret uv run mock-mcp --config monthly-report

# from a .env (gitignored)
echo "BEARER_TOKEN=my-secret" >> .env
uv run mock-mcp --config monthly-report
```

`BEARER_TOKEN` isn't a magic name — it's just whatever string you put in `token_env`. Use a profile-specific name (`MONTHLY_REPORT_TOKEN`, `INVENTORY_TOKEN`, etc.) when running multiple authenticated profiles side by side.

## Calling an authenticated route

```bash
curl -H "Authorization: Bearer mock-test-token" \
  "http://localhost:8001/reports/generate?report_month=2025-06"
```

Without the header:

```
$ curl -i "http://localhost:8001/reports/generate?report_month=2025-06"
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
content-type: application/json

{"detail":"Invalid or missing bearer token"}
```

With a wrong token:

```
$ curl -i -H "Authorization: Bearer wrong" \
    "http://localhost:8001/reports/generate?report_month=2025-06"
HTTP/1.1 401 Unauthorized
{"detail":"Invalid or missing bearer token"}
```

## Auth flow through MCP

The `/mcp` endpoint itself is unauthenticated — the MCP transport is open. But when an MCP client calls a tool, the framework dispatches that call to the underlying authored HTTP route, **and that route is auth-protected**. So auth still gets enforced, just one layer in.

The way it works:

1. MCP client (e.g. [Forbin](pairing-with-forbin.md)) sends `POST /mcp` with a `tools/call` request. The client should include its `Authorization: Bearer <token>` header on this request.
2. The framework's `/mcp` handler accepts the call, looks up the operation, and **forwards allowlisted headers** when dispatching to the authored route.
3. The authored route's auth dependency checks the forwarded `Authorization` header — same as if the client had hit the route directly.

The header allowlist is configured by `x-mock-mcp.forward_headers` (defaults to `[authorization]`):

```yaml
x-mock-mcp:
  forward_headers: [authorization]    # default; add more as needed
```

If your auth depends on additional headers (e.g. `X-API-Key`, `X-Tenant-ID`), add them here. Anything not in the allowlist is dropped during dispatch.

## Disabling auth entirely

Just omit the `x-mock-auth` block:

```yaml
openapi: 3.1.0
info:
  title: My Open Mock
  version: 1.0.0

x-mock-port: 8003
# (no x-mock-auth — every authored route is open)

x-mock-mcp:
  exclude_tags: [root, health]

paths:
  ...
```

The bundled `inventory-briefing.yaml` profile is built this way and serves as a working example.

## Per-route auth (not currently supported)

`x-mock-auth` is global to the profile — all authored routes share the same auth posture. There's no per-route override today. If you need a mix (some routes protected, some open), the workarounds are:

- Split into two profiles on different ports.
- Use a single profile with auth on, then add a thin proxy in front for the open routes.

Per-route auth is on the radar for later — see [FUTURE.md](FUTURE.md) if it matters to you.

## Common gotchas

| Symptom                                                              | Likely cause                                                                                  |
|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| `401 Invalid or missing bearer token` when you sent the right token  | Header name typo (must be `Authorization`), missing `Bearer ` prefix, or extra whitespace     |
| MCP `tools/call` returns 401 even though Forbin shows the token set  | Token not making it through MCP's header forwarding — confirm `x-mock-mcp.forward_headers` includes `authorization` (case-insensitive) |
| Default token works locally, env override doesn't on Fly/K8s         | Env var name in the deployment doesn't match `token_env` in the YAML                          |
| Server starts but every request 401s                                 | `default` is empty AND `token_env` env var isn't set — the loader should reject this at startup; if it doesn't, file an issue |
| Clients other than Forbin / curl can't auth                          | Some MCP clients don't surface a way to set custom headers; check the client's docs           |

## Implementation pointers

- The dependency factory is in [`app/auth.py`](../app/auth.py) (~50 lines). It builds a FastAPI `Depends(...)` callable from the `x-mock-auth` dict.
- The loader wires it up in [`app/loader.py:build_app`](../app/loader.py) — the dependency is attached to every route registered from `paths:`.
- The MCP header-forwarding lives in [`app/mcp_server.py`](../app/mcp_server.py); look for `forward_set` and the `headers` dict assembled in `_call_tool`.
