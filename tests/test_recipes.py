"""Tests for app/mock/recipes.py."""

from __future__ import annotations

import pytest

from app.mock import recipes as r
from app.mock.recipes import Context

# ---- is_recipe / walk -------------------------------------------------------


def test_is_recipe_true_for_known_verb():
    assert r.is_recipe({"static": 1})
    assert r.is_recipe({"random_int": [1, 2]})


def test_is_recipe_false_for_multi_key_dict():
    assert not r.is_recipe({"static": 1, "extra": 2})


def test_is_recipe_false_for_unknown_verb():
    assert not r.is_recipe({"made_up_verb": 1})


def test_is_recipe_false_for_non_dict():
    assert not r.is_recipe([1, 2])
    assert not r.is_recipe(42)
    assert not r.is_recipe("hi")


def test_walk_passes_through_literals(ctx: Context):
    assert r.walk("hello", ctx) == "hello"
    assert r.walk(42, ctx) == 42
    assert r.walk(True, ctx) is True
    assert r.walk(None, ctx) is None


def test_walk_evaluates_nested_recipes(ctx: Context):
    tree = {
        "a": {"static": "x"},
        "b": [{"static": 1}, {"static": 2}, "literal"],
        "c": {"nested": {"static": True}},
    }
    out = r.walk(tree, ctx)
    assert out == {"a": "x", "b": [1, 2, "literal"], "c": {"nested": True}}


# ---- static -----------------------------------------------------------------


def test_static_returns_value(ctx: Context):
    assert r.evaluate({"static": 0}, ctx) == 0
    assert r.evaluate({"static": [1, 2, 3]}, ctx) == [1, 2, 3]
    assert r.evaluate({"static": None}, ctx) is None


# ---- random_int -------------------------------------------------------------


def test_random_int_within_bounds(ctx: Context):
    for _ in range(20):
        v = r.evaluate({"random_int": [10, 20]}, ctx)
        assert isinstance(v, int)
        assert 10 <= v <= 20


def test_random_int_rejects_non_pair(ctx: Context):
    with pytest.raises(ValueError):
        r.evaluate({"random_int": [1]}, ctx)


def test_random_int_evaluates_expression_bounds(ctx: Context):
    # bound expressions are evaluated via the derived evaluator
    v = r.evaluate({"random_int": [{"to_int": {"mul": [10, 2]}}, 30]}, ctx)
    assert 20 <= v <= 30


# ---- random_float -----------------------------------------------------------


def test_random_float_raw(ctx: Context):
    v = r.evaluate({"random_float": [0.0, 1.0]}, ctx)
    assert isinstance(v, float)
    assert 0.0 <= v <= 1.0


def test_random_float_with_round(ctx: Context):
    v = r.evaluate({"random_float": {"range": [0.0, 100.0], "round": 2}}, ctx)
    # round to 2 decimals → at most 2 digits after the dot
    assert isinstance(v, float)
    assert v == round(v, 2)


# ---- random_choice ----------------------------------------------------------


def test_random_choice_picks_from_list(ctx: Context):
    options = ["a", "b", "c"]
    for _ in range(10):
        assert r.evaluate({"random_choice": options}, ctx) in options


# ---- faker ------------------------------------------------------------------


def test_faker_short_form(ctx: Context):
    out = r.evaluate({"faker": "company"}, ctx)
    assert isinstance(out, str)
    assert len(out) > 0


def test_faker_long_form_with_kwargs(ctx: Context):
    out = r.evaluate(
        {"faker": {"provider": "pyint", "kwargs": {"min_value": 100, "max_value": 200}}},
        ctx,
    )
    assert isinstance(out, int)
    assert 100 <= out <= 200


# ---- from -------------------------------------------------------------------


def test_from_short_form_pulls_query(ctx: Context):
    ctx.request["query"]["report_month"] = "2025-06"
    assert r.evaluate({"from": "query.report_month"}, ctx) == "2025-06"


def test_from_long_form_with_map(ctx: Context):
    ctx.request["query"]["use_preview_db"] = True
    out = r.evaluate(
        {"from": {"path": "query.use_preview_db", "map": {True: "preview", False: "prod"}}},
        ctx,
    )
    assert out == "preview"


def test_from_map_handles_string_keys_for_bool_values(ctx: Context):
    # YAML often parses True/False as strings or actual bools depending on quoting
    ctx.request["query"]["flag"] = False
    out = r.evaluate(
        {"from": {"path": "query.flag", "map": {"true": "yes", "false": "no"}}},
        ctx,
    )
    assert out == "no"


def test_from_with_slice(ctx: Context):
    ctx.request["query"]["report_month"] = "2025-06"
    out = r.evaluate({"from": {"path": "query.report_month", "slice": [0, 4]}}, ctx)
    assert out == "2025"


def test_from_with_split_index(ctx: Context):
    ctx.request["query"]["report_month"] = "2025-06"
    out = r.evaluate(
        {"from": {"path": "query.report_month", "split": "-", "index": 1}},
        ctx,
    )
    assert out == "06"


def test_from_missing_path_raises(ctx: Context):
    with pytest.raises(KeyError):
        r.evaluate({"from": "query.missing"}, ctx)


def test_from_unmapped_value_raises(ctx: Context):
    ctx.request["query"]["x"] = "weird"
    with pytest.raises(ValueError):
        r.evaluate({"from": {"path": "query.x", "map": {"a": 1}}}, ctx)


# ---- now --------------------------------------------------------------------


def test_now_returns_iso_utc(ctx: Context):
    out = r.evaluate({"now": True}, ctx)
    assert isinstance(out, str)
    # ISO-8601 with timezone offset
    assert "T" in out and ("+" in out or "Z" in out)


# ---- template ---------------------------------------------------------------


def test_template_substitutes_vars(ctx: Context):
    ctx.request["query"]["year"] = "2025"
    out = r.evaluate(
        {
            "template": {
                "format": "year={y}/month={m}",
                "vars": {"y": {"from": "query.year"}, "m": {"static": "06"}},
            }
        },
        ctx,
    )
    assert out == "year=2025/month=06"


def test_template_requires_format_field(ctx: Context):
    with pytest.raises(ValueError):
        r.evaluate({"template": {"vars": {}}}, ctx)


def test_template_resolves_derived_expressions_in_vars(ctx: Context):
    """`{ref: ...}` inside template vars must be evaluated, not str-formatted as a literal dict."""
    ctx.root = {"metrics": {"total": 12345.67}}
    out = r.evaluate(
        {
            "template": {
                "format": "Total: ${total}",
                "vars": {"total": {"ref": "/metrics/total"}},
            }
        },
        ctx,
    )
    assert out == "Total: $12345.67"
