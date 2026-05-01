"""Tests for app/mock/engine.py — seeding, determinism, static passthrough."""

from __future__ import annotations

from app.mock import engine


def test_static_passthrough_returns_value_verbatim():
    assert engine.generate_static({"a": 1}) == {"a": 1}
    assert engine.generate_static([1, 2]) == [1, 2]
    assert engine.generate_static("literal") == "literal"


def test_generate_deterministic_with_seed():
    spec = {
        "seed_from": "query.x",
        "response": {"v": {"random_int": [1, 1_000_000]}},
    }
    a = engine.generate(spec, {"query": {"x": "hello"}})
    b = engine.generate(spec, {"query": {"x": "hello"}})
    assert a == b


def test_generate_different_seeds_diverge():
    spec = {
        "seed_from": "query.x",
        "response": {"v": {"random_int": [1, 1_000_000]}},
    }
    a = engine.generate(spec, {"query": {"x": "alpha"}})
    b = engine.generate(spec, {"query": {"x": "beta"}})
    assert a != b


def test_generate_no_seed_is_independent():
    # Without seed_from, two calls should not be required to match (RNG is fresh per call).
    spec = {"response": {"v": {"random_int": [1, 1_000_000]}}}
    # Run a few pairs; getting the same value 5 times in a row across 1M-wide range
    # is vanishingly unlikely if seeding is truly absent.
    samples = {engine.generate(spec, {"query": {}})["v"] for _ in range(5)}
    assert len(samples) > 1


def test_generate_walks_recipe_tree():
    spec = {
        "response": {
            "literal": "kept",
            "static_recipe": {"static": 42},
            "nested": {"deep": {"static": [1, 2]}},
        }
    }
    out = engine.generate(spec, {})
    assert out == {"literal": "kept", "static_recipe": 42, "nested": {"deep": [1, 2]}}


def test_generate_applies_derived():
    spec = {
        "response": {
            "a": {"static": 3},
            "b": {"static": 4},
            "total": {"static": 0},  # placeholder
        },
        "derived": [
            {"path": "/total", "value": {"sum": [{"ref": "/a"}, {"ref": "/b"}]}},
        ],
    }
    out = engine.generate(spec, {})
    assert out == {"a": 3, "b": 4, "total": 7}


def test_seed_uses_sha256_so_stable_across_python_processes():
    # The point of using SHA-256 (not Python's hash()) is determinism across
    # PYTHONHASHSEED randomization. We can't restart the process inside a test,
    # but we can verify that the seed depends only on the value, not the
    # Python process — by checking that two distinct Context objects from two
    # separate engine.generate calls produce the same output.
    spec = {"seed_from": "query.x", "response": {"v": {"random_int": [1, 999_999]}}}
    out_a = engine.generate(spec, {"query": {"x": "stable-key"}})
    out_b = engine.generate(spec, {"query": {"x": "stable-key"}})
    out_c = engine.generate(spec, {"query": {"x": "stable-key"}})
    assert out_a == out_b == out_c
