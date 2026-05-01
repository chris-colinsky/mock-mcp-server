# Future direction

A scratchpad for where this project might go after v0.1.x. Nothing here is committed; treat it as an idea board for future scoping.

## Distribution

The current "clone the repo and `uv run`" workflow fits the framework's shape today. Long-term, the natural distribution model is **a container image or `docker-compose` stack** that you self-host, in the same vein as:

- **[Langfuse](https://github.com/langfuse/langfuse)** — observability platform; docker-compose stack with Postgres + ClickHouse + app.
- **[Infisical](https://github.com/Infisical/infisical)** — secrets management; docker-compose stack with Postgres + Redis + app.
- **[Bifrost](https://github.com/maximhq/bifrost)** — LLM gateway; container with optional persistence.

What that buys us:

- One-line install (`docker compose up`) instead of "clone the repo, install uv, sync deps, write a config…".
- Configs live in a mounted volume or a backing database, not interleaved with the code.
- Multi-instance is straightforward — spawn N mocks on different ports from one stack.
- Updates are a `docker compose pull` away, and version pinning is explicit.

## Near-term: interactive CLI (v0.2)

A natural intermediate step before the browser UI: an **interactive CLI that manages one or more running mock servers**, in the same UX family as Forbin. Right size for "I'm authoring profiles and want to flip between them without juggling terminals."

### Why this is not throwaway work

The view layer changes between TUI and browser, but the **orchestration kernel underneath does not**. Profile registry, start/stop/restart, status, log tailing, port allocation — all of those carry forward unchanged into the eventual web orchestrator. Building the kernel against a TUI consumer first is a cheaper way to validate the contract before the heavier browser frontend lands.

### Sketch

- **Runtime CLI stays as-is.** `mock-mcp --config <name>` continues to be the headless / CI entry point. No coupling between the runtime and the manager.
- **New binary** (working name `mock-mcp-studio`). Lists registered profiles, lifecycle ops on each, log tailing, schema-driven test panel for tools — same Rich/Textual stack Forbin uses, so install footprint stays familiar.
- **Backend:** `subprocess.Popen` per profile, with structured log files in `~/.mock-mcp/logs/<profile>.log`. State (registered profiles, last-known status, ports) in `~/.mock-mcp/state.json` or a tiny SQLite file.
- **tmux is optional.** "Attach to a running profile in tmux" can be a one-key shortcut for users who already have tmux installed, but **not a hard dependency** — that would tax Windows/WSL users for no gain over plain log tailing. Mirrors Forbin's posture on POSIX-only features.
- **Test panel.** Reuse Forbin's MCP-client logic (or depend on Forbin directly) so "browse tools, call one, see the response" works against any locally-managed profile without leaving the studio.

### Open design calls for v0.2

- **Separate repo or sub-package?** Either works; sub-package keeps shared code (profile schema, validation) trivial to reuse, separate repo makes the runtime/kernel boundary visible. Lean: sub-package now, split later if it grows.
- **Profile registry source of truth:** does the studio scan a configured directory, or does it own a registry that points at YAML paths? Directory-scanning is simpler; explicit registry is more flexible (multiple roots, named environments per profile).
- **Forbin reuse vs. duplicate:** the test-panel feature overlaps almost completely with Forbin's tool browser. Cleanest is to depend on Forbin's client code rather than fork it.

## Browser UI

A web UI on top of the runtime. The CLI remains for headless / CI use, but interactive authoring lives in the browser.

### Authoring

- **In-app IDE** built around [Monaco](https://github.com/microsoft/monaco-editor) (the editor that powers VS Code).
- The JSON Schema in `schemas/mock-mcp-config.schema.json` plugs straight into Monaco's `setDiagnosticsOptions` for autocomplete, hover docs, and lint markers — no extra schema work needed.
- Live validation against `app/loader.py` semantics on save (catches the things JSON Schema can't, e.g. "must define exactly one of `x-mock-static`/`x-mock-dynamic`"). Same code path as `make validate-configs`.
- Profile-level diffs, version history, optional git-backed storage so configs are reviewable as PRs.

### Operating

- **Spawn / stop mock instances on demand.** Each profile becomes a container instance on a chosen port; the UI lists what's running and lets you start/stop/restart without touching a terminal.
- **Test panel.** Pick a tool, fill in arguments via a form generated from the JSON Schema, see the response inline. (Forbin shows what this experience feels like as a TUI; the browser version is the same idea with richer rendering.)
- **Activity log.** Per-instance request log so you can see what an agent under eval is actually calling.

## Architecture sketch

The biggest design fork is whether to evolve the current Python app into a UI-bearing monolith or split into two independently-deployable pieces:

```
┌────────────────────────────────────┐        ┌──────────────────────────────────┐
│  control plane (orchestrator+UI)   │        │  runtime kernel (this framework)  │
│                                    │        │                                   │
│  - browser UI (Monaco, React/Vue)  │ HTTP   │  - app/loader, app/mcp_server,    │
│  - config storage (db or git)      │ + DB   │    app/mock/*  (today's code)     │
│  - Docker / Compose orchestration  │        │  - one container per profile      │
│  - auth, multi-tenant concerns     │        │  - reads config, serves /mcp      │
└────────────────────────────────────┘        └──────────────────────────────────┘
```

Recommendation: **lean toward the split.** The current framework is small, focused, and stable; locking it down as a runtime kernel lets the orchestrator iterate fast without dragging the runtime along. It also matches the model of the OSS projects above (Langfuse separates worker / web / database; Infisical separates app / Postgres / Redis).

## Free wins from work already shipped

These accelerate the future work without any porting:

- **JSON Schema** (`schemas/mock-mcp-config.schema.json`) — direct Monaco input.
- **OpenAPI surface** (`/openapi.json` per running mock) — the orchestrator can introspect any running profile to render preview UIs without bespoke wiring per profile.
- **`make validate-configs`** — same code path the browser IDE will use server-side for "save & validate" gating.
- **CHANGELOG-driven release notes + GitHub release workflow** — already wired; container image build/push step slots into the same workflow alongside the existing wheel build.

## Open questions to revisit when this work starts

- **Config storage:** filesystem (mounted volume), database, or git-backed? Git-backed gives free history and PR review; database gives a cleaner UX but reinvents version control.
- **Auth:** the orchestrator is sensitive (it spawns containers). OIDC? Local users + sessions? Inherit from a parent identity provider?
- **Multi-tenant?** Or single-tenant self-hosted only? Affects DB schema, auth, network isolation between spawned instances.
- **Frontend stack:** React + Vite + Monaco is the safe choice; Svelte/Solid are smaller but less ecosystem. TypeScript end-to-end is non-negotiable.
- **Naming:** "mock-mcp-server" describes the runtime kernel cleanly. The platform layered on top probably wants a different name (mock-mcp-studio? mock-mcp-platform?). Naming things now anchors the architecture.
- **Validator extensibility (`x-mock-validate`).** Today, anything beyond standard OAS keywords (`pattern`, `enum`, `minimum`, `format`, …) requires a Python function added to `app/validators.py` and registered in the `VALIDATORS` dict. Fine for a developer-authored project but doesn't scale to a UI where non-developers create profiles. Three plausible directions:
  1. **Curated registry.** Ship a generous catalog of built-ins (date ranges, currency, country codes, business-day rules, JSON-schema-format extensions), document it well, and treat "bring your own validator" as an advanced power-user feature reached only by editing the package source. Lowest risk, lowest expressiveness.
  2. **Predicate DSL in YAML.** Extend `x-mock-validate` to accept boolean expressions composed of our existing operators (`ref`, `sum`, comparators, regex match, etc.). Composes cleanly with the derived DSL we already have. Authoring still happens in YAML — no code execution. Limited to what the operators express, which is the whole point.
  3. **Sandboxed user code.** Allow inline Python (or a smaller language like Lua / CEL / Starlark) in the YAML, executed in a restricted sandbox at validation time. Most expressive, highest security risk, hardest to ship safely from a multi-tenant control plane.
  Recommendation: lean (1) + (2) — invest in the built-in catalog so most rules need no extension, then add the predicate DSL when the catalog hits its expressive limit. Skip (3) unless there's a concrete demand the DSL can't meet.

## Non-goals (worth being explicit about)

- **Not a hosted SaaS.** This is self-host-only by design; same posture as Langfuse Community / Infisical / Bifrost.
- **Not a generic API mocker.** The MCP-shaped tool surface is the point; if the use case doesn't involve agents calling tools, [Prism](https://github.com/stoplightio/prism), [Microcks](https://microcks.io/), or [mockoon](https://mockoon.com/) are better fits.
- **Not a replacement for production stubs.** This targets eval and local development, not load testing or contract testing in CI for the real upstream service.
