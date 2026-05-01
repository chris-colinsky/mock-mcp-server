# Pair with Forbin

[**Forbin**](https://github.com/chris-colinsky/forbin-mcp) is the companion repo to this one — an interactive CLI for testing remote MCP servers. It connects, lists tools, lets you inspect their schemas, and calls them with type-aware parameter prompts.

Both projects speak vanilla MCP, so no special integration is required.

```
┌──────────────────────────┐         MCP / HTTP          ┌──────────────────────┐
│   mock-mcp-server        │ ◄─────────────────────────► │   Forbin (CLI)       │
│   (this repo)            │   localhost:8001/mcp        │   forbin-mcp repo    │
│   serves authored YAML   │   localhost:8001/health     │   browse + call      │
└──────────────────────────┘                             └──────────────────────┘
```

## Walkthrough

```bash
# terminal 1 — run the mock
uv run mock-mcp --config monthly-report

# terminal 2 — install + run Forbin (one-time install)
pipx install forbin-mcp
# or: brew tap chris-colinsky/forbin-mcp && brew install forbin-mcp
forbin                                          # first run prompts for connection settings
```

When Forbin's first-run wizard asks for connection details, point it at your mock:

| Forbin field      | Value for `monthly-report` profile                                                   |
|-------------------|--------------------------------------------------------------------------------------|
| `MCP_SERVER_URL`  | `http://localhost:8001/mcp`                                                          |
| `MCP_HEALTH_URL`  | `http://localhost:8001/health` *(optional — Forbin probes it before connecting; useful if you put the mock on Fly/Render later)* |
| `MCP_TOKEN`       | `mock-test-token` *(or whatever you set via `BEARER_TOKEN`)*                         |

You'll land in Forbin's tool browser:

```
Available Tools

   1. generate_report - Generate Report

Commands:
  [number] - Select a tool
  [r]      - Run tool         (after selecting one)
  [d]      - View details     (after selecting one)
  ...
```

Press `1` → `r`, type `report_month=2025-06` at the prompt, and Forbin will route the call through MCP and pretty-print the synthesized response.

## Iterating on a profile

Tight feedback loop while authoring:

1. Edit `configs/<profile>.yaml`
2. Restart the mock (Ctrl-C, re-run `mock-mcp`)
3. In Forbin, press `r` again — same args, fresh response

If you have multiple mock profiles running on different ports, Forbin's profile/environment system lets you keep `local-mock`, `staging`, `prod` connection settings side-by-side and switch with `p` mid-session.

## Why this beats curl

- **No HTTP boilerplate.** No curl flags, no JSON-by-hand for MCP requests, no session-id management.
- **Schema inspection.** Press `d` to see the exact tool schema your agent will see — the same one this framework derives from your authored OAS. Useful sanity check that what's in your YAML matches what an agent will read.
- **Clipboard handoff.** Press `c` after a response to copy it; useful for diffing real-vs-mock outputs or pasting into bug reports.
- **Multi-profile parity.** Switch between mock and real server with `p` to verify your mock's responses match the real server's shape.

## Server-side log visibility

When Forbin makes a tool call, you'll see two log lines on the mock:

```
INFO:     127.0.0.1:54321 - "POST /mcp HTTP/1.1" 200 OK
INFO:     mcp dispatch generate_report -> "GET /reports/generate?report_month=2025-06" 200 (32ms)
```

The first is uvicorn's access log for the inbound MCP call. The second is mock-mcp's own dispatch log showing which authored route the tool fired and how long it took. The dispatch happens in-process via httpx ASGI (no real HTTP loopback), so without that log line you'd only see the outer call.

## Forbin's full docs

For the config wizard, profile management, CI usage, and so on: see [chris-colinsky/forbin-mcp](https://github.com/chris-colinsky/forbin-mcp).
