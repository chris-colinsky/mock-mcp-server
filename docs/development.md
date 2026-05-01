# Development

## Make targets

```bash
make help                  # full categorized list

# setup
make install               # runtime deps only
make install-dev           # runtime + dev deps (ruff, mypy, pre-commit, pytest)

# testing
make test                  # full pytest suite
make test-coverage         # with HTML coverage report at htmlcov/index.html
make validate-configs      # load + build every YAML profile in configs/

# code quality
make lint                  # ruff check
make format                # ruff format + ruff check --fix
make format-check          # check formatting without modifying files
make typecheck             # mypy
make check                 # format-check + lint + typecheck + test + validate-configs
make ci                    # alias for `check` — used by GitHub Actions

# running
make run                   # run the bundled monthly-report profile
make run-help              # show CLI help

# pre-commit
make pre-commit-install    # install the git hook
make pre-commit-run        # run all hooks against all files

# packaging
make clean                 # remove build artifacts and caches
make build                 # build sdist + wheel into dist/
make publish-test          # upload to TestPyPI
make publish               # upload to PyPI
```

## Test layout

```
tests/
├── conftest.py             # shared fixtures (deterministic Context, etc.)
├── test_recipes.py         # leaf-recipe coverage
├── test_derived.py         # derived-op + JSON Pointer coverage
├── test_engine.py          # determinism / seeding
├── test_validators.py      # built-in request validators
├── test_mcp_tools.py       # OAS → MCP tool-list conversion
├── test_configs.py         # parametrized: load + build every config
└── test_e2e.py             # FastAPI TestClient against bundled profiles
```

`test_configs.py` is special: it parametrizes over every `*.yaml` and `*.yml` under `configs/`, so adding a new profile automatically gets it covered. Pre-commit runs this on YAML or app changes; CI runs it on every push.

## Pre-commit hooks

`.pre-commit-config.yaml`:

- `pre-commit-hooks` — trailing whitespace, EOF newlines, YAML/JSON/TOML check, merge-conflict markers, debug statements, mixed line endings.
- `ruff` (with `--fix`) and `ruff-format`.
- `mypy` with `--ignore-missing-imports` (matches the `[tool.mypy]` config in `pyproject.toml`).
- A local hook that runs `validate-configs` when YAML or app files change.

Install once with `make pre-commit-install`; runs automatically on every `git commit`.

## CI

`.github/workflows/ci.yml` — fires on every push and pull request to `main`:

1. Install Python 3.13 + uv.
2. `uv sync` (runtime + dev).
3. Format check (`ruff format --check`).
4. Lint (`ruff check`).
5. Type check (`mypy app`).
6. Validate configs (`pytest tests/test_configs.py`).
7. Full test suite (`pytest`).

Fails fast if any step doesn't pass.

## Release workflow

`.github/workflows/release.yml` — fires on `v*.*.*` tag pushes:

1. Run CI (test + format + lint + typecheck).
2. Build sdist + wheel.
3. Extract the matching version section from `CHANGELOG.md`.
4. Create a GitHub release with the extracted notes and the built artifacts.

Stub jobs for PyPI Trusted Publishing and a Homebrew tap update are commented in the workflow; uncomment when you decide to ship as installable.

To cut a release:

1. Move `[Unreleased]` content under a new `## [X.Y.Z] - YYYY-MM-DD` section in `CHANGELOG.md`.
2. Bump `pyproject.toml` `version` to `X.Y.Z`.
3. Sync `uv.lock` (`uv sync` will do it).
4. Commit, push to `main`.
5. Tag: `git tag -a vX.Y.Z -m "..."` and `git push origin vX.Y.Z`.
6. Watch Actions tab; release page lands at `releases/tag/vX.Y.Z`.

## Branching

Convention from `~/.claude/CLAUDE.md`:

- `feature/<short-kebab-desc>` — new functionality
- `fix/<short-kebab-desc>` — bug fixes
- `refactor/<short-kebab-desc>` — restructuring without behavior change
- `chore/<short-kebab-desc>` — tooling, deps, config, housekeeping
- `schema/<short-kebab-desc>` — database / data model changes
- `release/v<X.Y.Z>` — accumulating changes for a specific upcoming release

For ticketed work: `feature/PROJ-123-user-export`.

## Commit messages

50/72 rule (see `~/.claude/CLAUDE.md`):

- Subject ≤50 chars (hard cap 72), imperative, no trailing period.
- Blank line, then body wrapped at 72.
- Body explains *what* and *why*, not *how*.
- No `Co-Authored-By: Claude` trailer or `🤖 Generated with Claude Code` footer.

If the change can't be summarized in ≤50 chars, prefer splitting into multiple commits over a long subject.

## Key invariants to preserve

When changing the framework, hold these:

1. **OAS is the source of truth for the MCP tool schema.** `app/mcp_server.py:build_tools` walks the authored OAS dict directly to produce the MCP tool list — it does NOT introspect FastAPI routes. If you need MCP-visible behavior to change, change the YAML, not the FastAPI route registration.
2. **Determinism via `seed_from`.** `app/mock/engine.py` SHA-256-hashes the resolved request value to seed both Python's RNG and Faker. SHA-256 (not Python's `hash()`) is deliberate — survives `PYTHONHASHSEED` randomization across processes. Don't introduce other RNG sources or unseeded `random` calls.
3. **`x-mock-static` XOR `x-mock-dynamic` per operation.** The validator in `app/loader.py:_validate` enforces this. Adding new mock-data modes? Update both the validator and `_register_route`'s dispatch.

## Acceptance bar for new features

The bundled `configs/monthly-report.yaml` profile must continue to produce a response where:

- `total_brands == sum(brands_by_platform.values())`
- `YES + NO + DONE == total_brands`
- Same `report_month` → same response (modulo `generated_at`)

`tests/test_e2e.py` enforces all three.
