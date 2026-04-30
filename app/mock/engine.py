"""
Orchestrates a single mock response evaluation.

Workflow:
  1. Build a deterministic seed from `seed_from` (if provided) using SHA-256
     so determinism survives PYTHONHASHSEED randomization.
  2. Walk the `response` tree, evaluating recipes in order they appear.
  3. Apply `derived` entries in order, each writing back into the tree.
"""
from __future__ import annotations

import hashlib
from typing import Any

from faker import Faker

from app.mock import derived as derived_mod
from app.mock import recipes as recipes_mod
from app.mock.recipes import Context


def generate(spec: dict, request: dict) -> Any:
    """
    Generate a mock response from an x-mock-dynamic spec.

    spec keys:
      - seed_from: str | None — request path (e.g. "query.report_month")
      - response: any — recipe tree
      - derived: list[dict] — derived expressions to apply post-walk
    """
    seed = _seed_from(spec.get("seed_from"), request)
    rng = _make_rng(seed)
    faker = Faker()
    if seed is not None:
        Faker.seed(seed)
        faker.seed_instance(seed)

    ctx = Context(rng=rng, faker=faker, request=request)

    # Wire recipes ↔ derived so each can call into the other without circular imports.
    ctx.expr_eval = derived_mod.evaluate
    ctx.recipe_eval = recipes_mod.evaluate  # used by derived to evaluate leaf recipes

    response = recipes_mod.walk(spec.get("response", {}), ctx)
    ctx.root = response

    derived = spec.get("derived") or []
    if derived:
        derived_mod.apply(response, derived, ctx)

    return response


def generate_static(value: Any) -> Any:
    """Static responses pass through verbatim."""
    return value


# -- seed handling --


def _seed_from(path: str | None, request: dict) -> int | None:
    if not path:
        return None
    parts = path.split(".")
    cur: Any = request
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return _stable_hash(str(cur))


def _stable_hash(s: str) -> int:
    """SHA-256 → first 8 bytes → unsigned int. Stable across processes."""
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _make_rng(seed: int | None):
    import random

    return random.Random(seed)
