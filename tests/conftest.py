"""Shared fixtures for the test suite."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from faker import Faker

from app.mock import derived as derived_mod
from app.mock import recipes as recipes_mod
from app.mock.recipes import Context


@pytest.fixture
def ctx() -> Context:
    """A deterministic eval context with a fixed RNG seed and empty request."""
    rng = random.Random(0)
    Faker.seed(0)
    fake = Faker()
    fake.seed_instance(0)
    c = Context(rng=rng, faker=fake, request={"query": {}, "path": {}})
    c.expr_eval = derived_mod.evaluate
    c.recipe_eval = recipes_mod.evaluate
    return c


@pytest.fixture
def utc_now() -> datetime:
    return datetime.now(UTC)
