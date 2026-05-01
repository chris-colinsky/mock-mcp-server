"""Tests for app/mock/derived.py."""

from __future__ import annotations

import pytest

from app.mock import derived as d
from app.mock.recipes import Context


def _root_ctx(ctx: Context, root: dict) -> Context:
    ctx.root = root
    return ctx


# ---- JSON Pointer get/set/delete -------------------------------------------


def test_get_simple(ctx: Context):
    ctx.root = {"a": {"b": 1}}
    assert d._get(ctx.root, "/a/b") == 1


def test_get_through_list(ctx: Context):
    ctx.root = {"a": [{"x": 10}, {"x": 20}]}
    assert d._get(ctx.root, "/a/1/x") == 20


def test_get_missing_raises(ctx: Context):
    ctx.root = {"a": {}}
    with pytest.raises(KeyError):
        d._get(ctx.root, "/a/missing")


def test_set_creates_intermediate_dicts(ctx: Context):
    root: dict = {}
    d._set(root, "/a/b/c", 42)
    assert root == {"a": {"b": {"c": 42}}}


def test_set_overwrites_existing(ctx: Context):
    root = {"a": {"b": 1}}
    d._set(root, "/a/b", 99)
    assert root == {"a": {"b": 99}}


def test_delete_removes_key(ctx: Context):
    root = {"a": {"b": 1, "c": 2}}
    d._delete(root, "/a/b")
    assert root == {"a": {"c": 2}}


def test_delete_missing_is_noop(ctx: Context):
    root = {"a": {}}
    d._delete(root, "/a/missing")
    assert root == {"a": {}}


def test_pointer_must_start_with_slash(ctx: Context):
    with pytest.raises(ValueError):
        d._split_pointer("a/b")


# ---- ref --------------------------------------------------------------------


def test_ref_returns_value(ctx: Context):
    _root_ctx(ctx, {"a": {"b": 7}})
    assert d.evaluate({"ref": "/a/b"}, ctx) == 7


# ---- arithmetic ops ---------------------------------------------------------


def test_sum_of_dict(ctx: Context):
    _root_ctx(ctx, {"counts": {"a": 1, "b": 2, "c": 3}})
    assert d.evaluate({"sum_of": "/counts"}, ctx) == 6


def test_sum_of_list(ctx: Context):
    _root_ctx(ctx, {"items": [10, 20, 30]})
    assert d.evaluate({"sum_of": "/items"}, ctx) == 60


def test_sum_of_rejects_non_container(ctx: Context):
    _root_ctx(ctx, {"x": 5})
    with pytest.raises(TypeError):
        d.evaluate({"sum_of": "/x"}, ctx)


def test_sum_of_args(ctx: Context):
    assert d.evaluate({"sum": [1, 2, 3]}, ctx) == 6


def test_sub_chain(ctx: Context):
    assert d.evaluate({"sub": [10, 3, 2]}, ctx) == 5


def test_mul(ctx: Context):
    assert d.evaluate({"mul": [2, 3, 4]}, ctx) == 24


def test_div(ctx: Context):
    assert d.evaluate({"div": [10, 4]}, ctx) == 2.5


def test_div_requires_two_args(ctx: Context):
    with pytest.raises(ValueError):
        d.evaluate({"div": [1, 2, 3]}, ctx)


def test_round(ctx: Context):
    assert d.evaluate({"round": {"value": 3.14159, "digits": 2}}, ctx) == 3.14


def test_to_int(ctx: Context):
    assert d.evaluate({"to_int": 3.7}, ctx) == 3


def test_min_max(ctx: Context):
    assert d.evaluate({"min": [3, 1, 2]}, ctx) == 1
    assert d.evaluate({"max": [3, 1, 2]}, ctx) == 3


# ---- nested expressions ----------------------------------------------------


def test_nested_ref_inside_arithmetic(ctx: Context):
    _root_ctx(ctx, {"a": 10, "b": 5})
    assert d.evaluate({"sub": [{"ref": "/a"}, {"ref": "/b"}]}, ctx) == 5


def test_recipe_inside_derived_value(ctx: Context):
    # random_int is a recipe but should be callable from derived expressions
    out = d.evaluate({"random_int": [1, 1]}, ctx)
    assert out == 1


# ---- apply (write-back) ----------------------------------------------------


def test_apply_writes_back(ctx: Context):
    response = {"a": 0, "b": 5}
    ctx.root = response
    d.apply(response, [{"path": "/a", "value": {"ref": "/b"}}], ctx)
    assert response == {"a": 5, "b": 5}


def test_apply_supports_delete(ctx: Context):
    response = {"a": 1, "scratch": 99}
    ctx.root = response
    d.apply(response, [{"delete": "/scratch"}], ctx)
    assert response == {"a": 1}


def test_apply_runs_in_declared_order(ctx: Context):
    response = {"a": 0, "b": 0}
    ctx.root = response
    d.apply(
        response,
        [
            {"path": "/a", "value": 7},
            {"path": "/b", "value": {"ref": "/a"}},  # reads /a after first entry wrote
        ],
        ctx,
    )
    assert response == {"a": 7, "b": 7}
