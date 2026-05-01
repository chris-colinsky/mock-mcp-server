# mock-mcp-server

A config-driven framework for standing up mock [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) servers — useful for agent evaluation harnesses (deepeval, custom eval loops) where the real tool calls are slow, flaky, or expensive.

You describe the API surface as **OpenAPI 3.1 + a few `x-mock-*` extensions** in a YAML file, drop it under `configs/`, and run it by name:

```bash
uv run mock-mcp --config monthly-report
```

The server speaks MCP at `/mcp` and serves the same tools as a regular HTTP API at the operation paths.

## Why

Real production tools often call many backend services and take seconds per invocation. When an evaluation harness invokes the same tool hundreds of times, runs become impractical. This framework gives you a **drop-in mock** that:

- Returns realistic, **deterministic** synthetic data for the same input (seeded RNG keyed off a request param).
- Speaks **MCP** at `/mcp` so eval harnesses can plug in without code changes.
- Emits the **same OpenAPI shape** as the real server, so the tool schema your agent sees is identical.
- Runs **instantly**, no external services touched.

Profiles are just YAML — no Python required to add a new mock.

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

The MCP endpoint is at `http://localhost:8001/mcp`. Standard FastAPI docs at `/docs`, `/redoc`, `/openapi.json`.

> **Tip:** Pair the running mock with [**Forbin**](https://github.com/chris-colinsky/forbin-mcp), an interactive MCP client, to browse and call your mock's tools without writing any client code. See [`docs/pairing-with-forbin.md`](docs/pairing-with-forbin.md).

## Documentation

Topic-organized reference under [`docs/`](docs/):

| Topic | Description |
|---|---|
| [Getting started](docs/getting-started.md) | Install, run, CLI flags, running multiple mocks in parallel. |
| [Config reference](docs/config-reference.md) | Every `x-mock-*` extension explained. |
| [Recipes](docs/recipes.md) | Leaf-recipe catalog (`random_int`, `faker`, `from`, `template`, …). |
| [Derived DSL](docs/derived.md) | Cross-field operators (`ref`, `sum`, `mul`, …) for invariants. |
| [Validation](docs/validation.md) | OAS keywords, built-in validators, writing your own. |
| [Auth](docs/auth.md) | Bearer-token setup, MCP header forwarding, common gotchas. |
| [Authoring strategies](docs/strategies.md) | Patterns: static vs dynamic, determinism, footguns, walkthrough. |
| [IDE setup](docs/ide-setup.md) | PyCharm and VS Code schema validation. |
| [Pairing with Forbin](docs/pairing-with-forbin.md) | Interactive client for testing mocks. |
| [Development](docs/development.md) | Makefile, tests, pre-commit, CI/release workflows. |
| [Examples](docs/examples/) | Walkthroughs of the bundled profiles. |
| [Future direction](docs/FUTURE.md) | Open design questions and sketches for v0.2+. |

[`docs/README.md`](docs/README.md) is the index page.

## Bundled profiles

| Profile | Demonstrates |
|---|---|
| [`configs/monthly-report.yaml`](configs/monthly-report.yaml) | Authenticated profile demonstrating every framework feature: dynamic recipes, derived DSL, sum/delta invariants, custom validators, bearer auth, seeded determinism. ([walkthrough](docs/examples/monthly-report.md)) |
| [`configs/inventory-briefing.yaml`](configs/inventory-briefing.yaml) | Open (no-auth) profile demonstrating variable-shape responses, template-in-derived for computed values, and Faker-generated structured records. ([walkthrough](docs/examples/inventory-briefing.md)) |

## Project layout

```
mock-mcp-server/
├── pyproject.toml
├── Makefile
├── .pre-commit-config.yaml
├── .github/workflows/      # CI + release
├── schemas/                # JSON Schema for x-mock-* extensions
├── configs/                # bundled profile YAMLs
├── app/                    # framework source
│   ├── __main__.py         # CLI
│   ├── loader.py           # OAS + x-mock-* → FastAPI
│   ├── mcp_server.py       # /mcp endpoint, OAS → MCP tools
│   ├── auth.py             # bearer auth
│   ├── validators.py       # custom validators
│   └── mock/               # response generation engine
├── tests/                  # ~95 tests
└── docs/                   # this README's deeper reference
```

## Limitations

- **Request body schemas** are accepted in OAS form but not deeply validated. Bodies pass through to dispatched calls verbatim. Open an issue if you need strict body validation.
- **No SSE streaming on `/mcp`** — only the streamable HTTP transport is mounted, and tool-call responses are buffered before being returned. Fine for stateless one-shot MCP calls.
- **`tools/call` returns the response body as `TextContent` (JSON string)** — matches what most MCP clients expect. Structured multi-block responses (images, embedded resources) aren't synthesized.
- **Distribution is "clone the repo," not `pip install`.** The `--config <name>` resolver looks under the repo's `configs/` dir; there's no good user experience for bring-your-own-config from an installed package today. See [`docs/FUTURE.md`](docs/FUTURE.md) for sketches of where this is heading.

## License

MIT (declared in [`pyproject.toml`](pyproject.toml)). A separate `LICENSE` file will land before the project is distributed beyond the source repo.
