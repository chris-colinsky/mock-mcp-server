# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (breaking — file paths)

- **`configs/terravita-sop.yaml` → `configs/inventory-briefing.yaml`.**
  The original profile name and content referenced a specific source
  project; both have been scrubbed and the file renamed to a generic
  `inventory-briefing` so the example doesn't leak the origin. If you
  were running the old profile by name, update your invocation:
  `mock-mcp --config inventory-briefing`.
- **Bearer auth removed from the renamed `inventory-briefing` profile.**
  The scrubbed profile is now intentionally open (no `x-mock-auth`
  block) so the two bundled profiles demonstrate both modes — auth in
  `monthly-report`, no auth in `inventory-briefing`. The earlier
  setup carried a confusing inline comment that contradicted the YAML.
- **`monthly-report` channel names** renamed from specific real-world
  affiliate platform names to generic `ChannelA` / `ChannelB` /
  `ChannelC` / `ChannelD` placeholders. Test suite is unaffected (it
  asserts on sums and structure, not specific names).
- **SKU prefix in `inventory-briefing`** changed from `TV-NNN-*` to
  `SKU-NNN-*`.

### Added

- **`docs/auth.md`** — dedicated reference for bearer-token auth.
  Covers the `x-mock-auth` block in detail, the documentary-vs-enforced
  distinction between `x-mock-auth` and OAS `security:` /
  `securitySchemes`, token-resolution rules, MCP header forwarding from
  `tools/call` through to dispatched routes, how to disable auth, and
  a gotchas table. The `config-reference.md` section on auth is now a
  brief summary that points here.

### Fixed

- **`/mcp` endpoint no longer dumps a `RuntimeError` per request.** The
  route was a normal FastAPI handler that delegated to
  `StreamableHTTPSessionManager.handle_request`, which writes the full
  ASGI response itself; FastAPI then tried to wrap our `None` return as
  a default JSONResponse, emitting a second `http.response.start` that
  uvicorn rejected. Capturing the ASGI messages from the session manager
  in-memory and returning a real FastAPI Response side-steps the
  collision. Trade-off: tool-call responses are buffered before return,
  no SSE streaming on `/mcp` — fine for stateless one-shot MCP calls.

### Added

- **MCP tool-dispatch logging.** Tool calls dispatch to FastAPI routes
  via in-process httpx ASGI transport, which means uvicorn's access log
  never sees them. New log line on the uvicorn logger surfaces each
  dispatch with method, URL, status, and latency:

  ```
  INFO:     mcp dispatch generate_report -> "GET /reports/generate?report_month=2025-06" 200 (32ms)
  ```

- **Documentation reorganization.** README slimmed to pitch +
  quickstart + project layout + limitations. Reference content moved
  into a topic-organized `docs/` directory:

  - `docs/getting-started.md` — install, run, CLI, multi-instance.
  - `docs/config-reference.md` — top-level + per-operation `x-mock-*` extensions.
  - `docs/recipes.md` — leaf-recipe catalog.
  - `docs/derived.md` — derived DSL operators and patterns.
  - `docs/validation.md` — three-tier validation guide (OAS keywords, built-in custom validators, writing your own).
  - `docs/strategies.md` — authoring patterns, footguns, debugging tips.
  - `docs/ide-setup.md` — PyCharm + VS Code schema setup.
  - `docs/pairing-with-forbin.md` — interactive client guide.
  - `docs/development.md` — make targets, tests, pre-commit, CI/release.
  - `docs/examples/monthly-report.md`, `docs/examples/inventory-briefing.md` — bundled profile walkthroughs.
  - `docs/README.md` — TOC / index.

- **`docs/FUTURE.md`** moved from a local draft into the committed
  `docs/` tree. Captures the v0.2 interactive-CLI sketch, the eventual
  browser-UI direction, container-image distribution plans, and open
  design questions including validator extensibility (curated registry
  vs predicate DSL vs sandboxed user code).

- **Inline comments in `configs/monthly-report.yaml`** explaining the
  two-stage validation flow (OAS pattern → `past_month_utc` custom
  validator).

### Changed

- **`x-mock-validate` validator catalog has a clearer extensibility
  story.** Documented in `docs/validation.md`: prefer OAS keywords for
  shape/range checks, use built-in custom validators for runtime-state
  rules, drop into Python only as a last resort. The current registry
  ships only `past_month_utc`; future directions for non-developer
  authoring tracked in `docs/FUTURE.md`.

## [0.1.1] - 2026-04-30

Development infrastructure, a second bundled profile, and one bug fix.
No changes to the framework's recipe/derived API — existing v0.1.0
profiles run unchanged.

### Added

- **Test suite** under `tests/` (~92 tests covering recipes, derived DSL,
  engine determinism, custom validators, MCP tool-list conversion, config
  loading, and end-to-end FastAPI TestClient flows).
- **`make` workflow** with `install-dev`, `test`, `test-coverage`, `lint`,
  `format`, `format-check`, `typecheck`, `validate-configs`, `check`,
  `pre-commit-install`, `clean`, `build`, `publish`, `run`. `make ci` is
  the entrypoint used by GitHub Actions.
- **`make validate-configs`** target: parametrized pytest that loads and
  builds every YAML profile under `configs/`. Catches typos in the
  `x-mock-*` surface that pure JSON-Schema validation can't.
- **Pre-commit hooks** (`.pre-commit-config.yaml`): trailing-whitespace,
  end-of-file-fixer, YAML/JSON/TOML check, ruff (with autofix),
  ruff-format, mypy, plus a local hook that runs `validate-configs` on
  YAML or app changes.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): format check, lint,
  type check, config validation, and full pytest suite on every push and
  pull request to `main`.
- **GitHub Actions release workflow** (`.github/workflows/release.yml`):
  on `v*.*.*` tag push, runs CI, builds sdist/wheel, extracts the
  matching section from CHANGELOG.md, and creates a GitHub release. Stub
  jobs for PyPI Trusted Publishing and a Homebrew tap update are
  commented out; uncomment when ready.
- **JSON Schema for IDE validation**
  (`schemas/mock-mcp-config.schema.json`). Profiles include a
  `# yaml-language-server: $schema=...` directive so editors with YAML
  schema support (VS Code via redhat.yaml, PyCharm via JSON Schema
  Mappings) flag unknown `x-mock-*` keys, typos, and bad shapes inline.
- **Ruff and mypy configuration** in `pyproject.toml` (line-length 100,
  py313 target, sensible mypy strictness).
- **Second bundled profile** — a Sales & Operations Planning–style
  briefing endpoint demonstrating a fixed-length SKU list with
  Faker-generated identifiers and a markdown LLM briefing rendered via
  `template` inside `derived` (pulls computed metrics through
  `{ref: ...}` vars). *Note: this profile shipped as
  `configs/terravita-sop.yaml` at v0.1.1 and was renamed and scrubbed
  to `configs/inventory-briefing.yaml` in a later release; see the
  Unreleased section.*

### Changed

- **`pyproject.toml` version corrected from `2.0.0` → `0.1.0`** to match
  the tagged release. Adds `[project.urls]`, classifiers, MIT license,
  and a `[dependency-groups] dev` group with ruff, mypy, pre-commit, and
  pytest.

### Fixed

- **`template` recipe now evaluates derived expressions inside `vars`.**
  Previously `{ref: /foo}` inside a template's vars was treated as a
  literal dict and rendered via `repr()`. It's now resolved through the
  derived-expression evaluator. Affects `template` recipes that
  reference other generated fields. Templates that only use request-side
  recipes (`from`, `faker`, `now`, `random_*`) are unchanged.

## [0.1.0] - 2026-04-30

Initial release. The repo started as a hardcoded mock of one specific
report-generation tool; this version is a generalized framework where any
mock server is described by an OpenAPI 3.1 YAML profile under `configs/`.

### Added

- **Config-driven framework.** Each profile is a standard OAS 3.1 document
  plus a small set of `x-mock-*` extensions that describe the mock behavior.
- **CLI** — `mock-mcp --config <profile>` resolves a profile name against
  `configs/<name>.yaml` and starts a server. Hard-errors with exit 2 on
  missing/invalid configs; no implicit default.
- **Top-level extensions:** `x-mock-port`, `x-mock-auth` (bearer with
  env-var override), `x-mock-mcp` (mount path, header forwarding,
  excluded tags).
- **Per-operation extensions:** `x-mock-static` (literal response),
  `x-mock-dynamic` (recipe tree + derived expressions), `x-mock-validate`
  (custom request validators). The framework enforces that each operation
  defines exactly one of `x-mock-static` or `x-mock-dynamic`.
- **Recipe catalog:** `static`, `random_int`, `random_float`,
  `random_choice`, `faker`, `from` (with `slice`, `split`, `map`),
  `now`, `template`.
- **Derived DSL:** `ref`, `sum`, `sum_of`, `sub`, `mul`, `div`, `round`,
  `to_int`, `min`, `max`, plus a `delete` action for cleaning up scratch
  fields. Supports cross-field invariants (sums, derived ratios,
  remainders).
- **Determinism via `seed_from`.** Resolved request values are SHA-256
  hashed to seed the RNG and Faker, so output is reproducible across
  processes (survives `PYTHONHASHSEED` randomization). The one
  intentionally non-deterministic recipe is `{now: true}`.
- **MCP server at `/mcp`,** built directly on the `mcp` Python SDK with
  the streamable HTTP transport. The MCP tool schema is built from the
  authored OAS dict — not from FastAPI route introspection — so the
  contract you write is what tools see.
- **Built-in custom validator:** `past_month_utc` (used by the bundled
  `monthly-report` profile to mirror the real server's "past month only"
  rule).
- **Bundled `monthly-report` profile** as the framework's expressiveness
  test. Reproduces the previous hardcoded behavior — same input ranges,
  same sum/delta invariants, same auth — entirely from YAML.
- **Comprehensive README** with feature reference, recipe and derived
  catalogs, authoring strategies, a "your first profile" walkthrough,
  and a guide for pairing with the [Forbin](https://github.com/chris-colinsky/forbin-mcp)
  interactive MCP CLI.

### Removed

- **`fastapi-mcp` dependency.** The previous hardcoded server delegated
  the MCP tool surface to fastapi-mcp's FastAPI-route introspection.
  That fit poorly once routes became config-driven, so the framework now
  talks MCP directly via the lower-level `mcp` SDK. No more monkey-patching
  or dynamic Pydantic-model generation.

[Unreleased]: https://github.com/chris-colinsky/mock-mcp-server/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/chris-colinsky/mock-mcp-server/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/chris-colinsky/mock-mcp-server/releases/tag/v0.1.0
