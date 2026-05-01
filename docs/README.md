# mock-mcp-server documentation

Topic-organized reference for authoring, running, and extending mock MCP server profiles.

## Start here

- **[Getting started](getting-started.md)** — install, run a bundled profile, CLI flags, running multiple mocks in parallel.

## Authoring profiles

- **[Config reference](config-reference.md)** — full structure: top-level `x-mock-*` extensions (`port`, `auth`, `mcp`) and per-operation extensions (`x-mock-static`, `x-mock-dynamic`, `x-mock-validate`).
- **[Recipes](recipes.md)** — the leaf-recipe catalog: `static`, `random_int`, `random_float`, `random_choice`, `faker`, `from`, `now`, `template`. With examples.
- **[Derived DSL](derived.md)** — operators (`ref`, `sum`, `sum_of`, `sub`, `mul`, `div`, `round`, `to_int`, `min`, `max`, `delete`), JSON Pointer paths, common patterns.
- **[Validation](validation.md)** — three tiers: OAS keywords (try first), built-in custom validators, writing your own.
- **[Authoring strategies](strategies.md)** — static vs. dynamic, determinism, cross-field invariants, YAML 1.1 footguns, debugging tips, bootstrapping from a real app, walkthrough of adding a new profile.

## Tooling and integration

- **[IDE setup](ide-setup.md)** — VS Code, PyCharm, and other yaml-language-server-aware editors. Schema-driven completions and lint markers as you author.
- **[Pairing with Forbin](pairing-with-forbin.md)** — the companion interactive MCP CLI. Browse, call, and iterate without writing client code.

## Examples

- **[monthly-report](examples/monthly-report.md)** — bundled profile that exercises every framework feature. The framework's smoke-test profile.
- **[terravita-sop](examples/terravita-sop.md)** — bundled profile mocking a real-world S&OP API. Shows the template-in-derived pattern and Faker-generated structured records.

## Project meta

- **[Development](development.md)** — Make targets, test layout, pre-commit hooks, CI/release workflows, branching and commit conventions, key invariants.
- **[Future direction](FUTURE.md)** — sketches and open design questions for distribution, browser UI, and validator extensibility. Working notes, not a roadmap.

## Where things live in the repo

```
mock-mcp-server/
├── README.md                       # high-level pitch + quickstart
├── docs/                           # this directory
├── configs/                        # profiles (one YAML each)
├── schemas/                        # JSON Schema for x-mock-* (IDE validation)
├── app/                            # framework source
│   ├── __main__.py                 # CLI: `mock-mcp --config <name>`
│   ├── loader.py                   # OAS + x-mock-* → FastAPI app
│   ├── mcp_server.py               # /mcp endpoint, OAS → MCP tools
│   ├── auth.py                     # bearer auth
│   ├── validators.py               # custom request validators
│   └── mock/                       # response generation engine
└── tests/                          # ~95 tests across unit + e2e
```
