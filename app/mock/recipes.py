"""
Leaf recipes for x-mock-dynamic.response.

A recipe is a single-key dict like `{random_int: [10, 30]}`. Anything
that is not a recipe (literal scalar, list, dict without a recipe key)
is returned as-is — except that nested dicts/lists are walked recursively
so recipes can sit anywhere in the response tree.

Bound values inside numeric recipes (e.g. `random_int: [5, {mul: ...}]`)
are evaluated via the derived expression evaluator, so recipes and
derived expressions compose. To avoid a circular import, the engine
injects the derived evaluator as `expr_eval` on the Context.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from faker import Faker

RECIPE_KEYS = {
    "static",
    "random_int",
    "random_float",
    "random_choice",
    "faker",
    "from",
    "now",
    "template",
}


@dataclass
class Context:
    """Evaluation context shared across one request."""

    rng: random.Random
    faker: Faker
    request: dict  # {"query": {...}, "path": {...}, "body": ...}
    root: dict = field(default_factory=dict)  # mutated as response is built; used by `ref`
    expr_eval: Callable[[Any, Context], Any] | None = None
    recipe_eval: Callable[[Any, Context], Any] | None = None


def is_recipe(node: Any) -> bool:
    """A recipe is a dict with exactly one key, and that key is a recipe verb."""
    return isinstance(node, dict) and len(node) == 1 and next(iter(node)) in RECIPE_KEYS


def walk(node: Any, ctx: Context) -> Any:
    """Recursively walk a response tree, evaluating recipes as encountered."""
    if is_recipe(node):
        return evaluate(node, ctx)
    if isinstance(node, dict):
        return {k: walk(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [walk(item, ctx) for item in node]
    return node


def evaluate(recipe: dict, ctx: Context) -> Any:
    """Evaluate a single recipe."""
    verb, arg = next(iter(recipe.items()))
    handler = _HANDLERS[verb]
    return handler(arg, ctx)


# -- recipe handlers --


def _h_static(arg: Any, ctx: Context) -> Any:
    return arg


def _h_random_int(arg: list, ctx: Context) -> int:
    lo, hi = _resolve_pair(arg, ctx)
    return ctx.rng.randint(int(lo), int(hi))


def _h_random_float(arg: Any, ctx: Context) -> float:
    """
    {random_float: [lo, hi]}                            → raw uniform
    {random_float: {range: [lo, hi], round: N}}         → rounded uniform
    """
    if isinstance(arg, dict):
        lo, hi = _resolve_pair(arg["range"], ctx)
        value = ctx.rng.uniform(float(lo), float(hi))
        if "round" in arg:
            value = round(value, int(arg["round"]))
        return value
    lo, hi = _resolve_pair(arg, ctx)
    return ctx.rng.uniform(float(lo), float(hi))


def _h_random_choice(arg: list, ctx: Context) -> Any:
    return ctx.rng.choice(arg)


def _h_faker(arg: Any, ctx: Context) -> Any:
    """
    {faker: "company.name"}
    {faker: {provider: "pyint", args: [], kwargs: {min_value: 1, max_value: 100}}}
    """
    if isinstance(arg, str):
        provider, args, kwargs = arg, [], {}
    else:
        provider = arg["provider"]
        args = arg.get("args", [])
        kwargs = arg.get("kwargs", {})
    method: Any = ctx.faker
    for part in provider.split("."):
        method = getattr(method, part)
    return method(*args, **kwargs)


def _h_from(arg: Any, ctx: Context) -> Any:
    """
    Pull a value from the request, with optional post-processing.

    {from: "query.report_month"}
    {from: {path: "query.use_preview_db", map: {true: preview, false: prod}}}
    {from: {path: "query.report_month", slice: [0, 4]}}                # "2025"
    {from: {path: "query.report_month", split: "-", index: 1}}         # "06"
    """
    if isinstance(arg, str):
        path = arg
        mapping = slice_spec = split_sep = split_index = None
    else:
        path = arg["path"]
        mapping = arg.get("map")
        slice_spec = arg.get("slice")
        split_sep = arg.get("split")
        split_index = arg.get("index")

    value = _resolve_request_path(path, ctx.request)

    if slice_spec is not None:
        if not isinstance(value, str) or not isinstance(slice_spec, list) or len(slice_spec) != 2:
            raise ValueError(
                f"from.slice requires a string value and [start, end] pair, got {value!r}"
            )
        value = value[slice_spec[0] : slice_spec[1]]

    if split_sep is not None:
        if split_index is None:
            raise ValueError("from.split requires an 'index' alongside 'split'")
        value = str(value).split(split_sep)[split_index]

    if mapping is not None:
        for k, v in mapping.items():
            if k == value or str(k).lower() == str(value).lower():
                return v
        raise ValueError(f"from.map has no entry for value {value!r}")

    return value


def _h_now(arg: Any, ctx: Context) -> str:
    """Always returns current ISO-8601 UTC timestamp. The one non-deterministic recipe."""
    return datetime.now(UTC).isoformat()


def _h_template(arg: dict, ctx: Context) -> str:
    """
    Python `str.format`-style interpolation with named substitutions.

    {template: {format: "year={year}/month={month}", vars: {year: <recipe-or-expr>, month: ...}}}

    Each var value may be a recipe ({faker, random_*, from, ...}), a derived
    expression ({ref, sum, ...}), or a literal. Derived expressions are useful
    for pulling already-generated response fields into the rendered string —
    e.g. {ref: /metrics/total} works once the response tree has populated
    `/metrics/total` (i.e. when the template is applied via a derived entry
    rather than during the initial response walk).
    """
    if not isinstance(arg, dict) or "format" not in arg:
        raise ValueError("template recipe requires {format: ..., vars: {...}}")
    fmt = arg["format"]
    vars_spec = arg.get("vars", {})
    resolved = {k: _resolve_template_var(v, ctx) for k, v in vars_spec.items()}
    return fmt.format(**resolved)


def _resolve_template_var(v: Any, ctx: Context) -> Any:
    """Resolve one template var: try recipe, then derived expression, else walk."""
    if is_recipe(v):
        return evaluate(v, ctx)
    if isinstance(v, dict) and ctx.expr_eval is not None:
        # Derived expression like {ref: ...}, {sum: ...}, etc.
        return ctx.expr_eval(v, ctx)
    return walk(v, ctx)


_HANDLERS = {
    "static": _h_static,
    "random_int": _h_random_int,
    "random_float": _h_random_float,
    "random_choice": _h_random_choice,
    "faker": _h_faker,
    "from": _h_from,
    "now": _h_now,
    "template": _h_template,
}


# -- helpers --


def _resolve_pair(arg: list, ctx: Context) -> tuple[Any, Any]:
    if not isinstance(arg, list) or len(arg) != 2:
        raise ValueError(f"expected [low, high] pair, got {arg!r}")
    lo = _maybe_expr(arg[0], ctx)
    hi = _maybe_expr(arg[1], ctx)
    return lo, hi


def _maybe_expr(value: Any, ctx: Context) -> Any:
    """If value looks like a derived expression, evaluate it; else return as-is."""
    if isinstance(value, dict) and ctx.expr_eval is not None:
        return ctx.expr_eval(value, ctx)
    return value


def _resolve_request_path(path: str, request: dict) -> Any:
    """Walk a dotted path like 'query.report_month' against the request dict."""
    parts = path.split(".")
    cur: Any = request
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(f"request path {path!r} not found")
        cur = cur[part]
    return cur
