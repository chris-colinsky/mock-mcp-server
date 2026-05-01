"""
Validation harness for every YAML profile under configs/.

The Makefile target `validate-configs` invokes this via pytest. CI runs it
on every push. If a config can't load + build, that's a bug in either the
YAML or the loader — and we want to catch it before it reaches a running
server.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.loader import build_app, load_config

CONFIG_DIR = Path(__file__).parent.parent / "configs"

CONFIG_FILES = sorted(p for p in CONFIG_DIR.glob("*.yaml")) + sorted(
    p for p in CONFIG_DIR.glob("*.yml")
)


@pytest.mark.parametrize("config_path", CONFIG_FILES, ids=lambda p: p.stem)
def test_config_loads_and_builds(config_path: Path) -> None:
    """Every profile must load via load_config and build a FastAPI app."""
    profile = config_path.stem
    config = load_config(profile)
    app = build_app(config)
    assert app is not None
    # the loader registered at least one route from the config
    user_routes = [r for r in app.routes if getattr(r, "path", "") not in ("/", "/health", "/mcp")]
    assert user_routes, f"{profile}: no operations registered"


def test_at_least_one_config_present() -> None:
    """Sanity: the repo should ship with at least one config to demo the framework."""
    assert CONFIG_FILES, "no configs found under configs/ — the repo should ship at least one"
