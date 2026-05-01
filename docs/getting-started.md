# Getting started

## Install

```bash
git clone https://github.com/chris-colinsky/mock-mcp-server.git
cd mock-mcp-server
uv sync                       # runtime + dev deps
# or:  uv sync --no-dev       # runtime only (just enough to run a profile)
```

Requires Python 3.13+ and [uv](https://github.com/astral-sh/uv).

## Run a profile

Two profiles ship with the repo. Run one:

```bash
uv run mock-mcp --config monthly-report
```

The server binds to the port declared in the YAML (`x-mock-port`) — `8001` for `monthly-report`, `8002` for `inventory-briefing`. Override with `--port`.

Hit it directly:

```bash
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
    "brands_by_platform": {"ChannelA": 26, "ChannelB": 37, "ChannelC": 25, "ChannelD": 16},
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

> **Tip:** Pair the running mock with [**Forbin**](https://github.com/chris-colinsky/forbin-mcp), an interactive MCP client, to browse and call your mock's tools without writing any client code. See [pairing-with-forbin.md](pairing-with-forbin.md).

## CLI

```
mock-mcp --config <profile> [--port N] [--host HOST] [--reload]
```

| flag       | required | default                                | notes |
|------------|----------|----------------------------------------|-------|
| `--config` | yes      | —                                      | Profile name. Resolved as `configs/<name>.yaml` (or `.yml`). No default — missing/invalid configs error out with exit code 2. |
| `--port`   | no       | from config (`x-mock-port`)            | Bind port. Overrides the config. |
| `--host`   | no       | `0.0.0.0`                              | Bind host. |
| `--reload` | no       | off                                    | Uvicorn auto-reload (dev only; watches `app/`, not `configs/`). |

Examples:

```bash
mock-mcp --config monthly-report
mock-mcp --config monthly-report --port 9001
mock-mcp --config some-other-profile --reload
```

If the profile doesn't exist:

```
$ mock-mcp --config foo
error: config profile not found: 'foo' (looked in /…/configs for foo.yaml or foo.yml)
$ echo $?
2
```

## Running multiple mocks side by side

Each profile binds its own port, so you can run as many in parallel as you want:

```bash
# terminal 1
uv run mock-mcp --config monthly-report          # → :8001

# terminal 2
uv run mock-mcp --config inventory-briefing      # → :8002

# terminal 3 (same profile twice, override the port)
uv run mock-mcp --config monthly-report --port 8011
```

No state is shared between processes; each is a fresh deterministic generator.

## Where to next

- [Add a new profile (walkthrough)](strategies.md#adding-a-new-profile) — write your first YAML.
- [Config reference](config-reference.md) — every `x-mock-*` extension explained.
- [Recipes](recipes.md) and [Derived DSL](derived.md) — the building blocks for dynamic responses.
- [Validation](validation.md) — OAS keywords, built-in custom validators, and writing your own.
- [Pairing with Forbin](pairing-with-forbin.md) — interactive client for testing.
