"""
Derived-field DSL for x-mock-dynamic.derived.

Each entry is `{path: <json-pointer>, value: <expression>}`. After the
response tree is generated, derived entries are evaluated in order
and written back into the tree at `path`.

Expressions:
  - literal: number, bool, string  → as-is
  - {ref: "/json/pointer"}          → look up a value from the in-progress response
  - {sum: [a, b, c]}                → sum of resolved arguments
  - {sum_of: "/path/to/dict-or-list"} → sum of values in container
  - {sub: [a, b, ...]}              → a - b - ...
  - {mul: [a, b, ...]}              → product
  - {div: [a, b]}                   → a / b
  - {round: {value: ..., digits: N}} → round(value, N)
  - {to_int: <expr>}                → int(value)
  - {min: [a, b, ...]} / {max}      → min/max
  - any leaf recipe (random_int etc) is also valid here — the engine
    injects the recipe evaluator as ctx.recipe_eval

Paths use RFC-6901 JSON Pointer ('/foo/0/bar'). `~0` and `~1` are
escapes for `~` and `/` respectively.
"""
from __future__ import annotations

from typing import Any


EXPR_KEYS = {
    "ref",
    "sum",
    "sum_of",
    "sub",
    "mul",
    "div",
    "round",
    "to_int",
    "min",
    "max",
}


def evaluate(node: Any, ctx) -> Any:
    """Evaluate a derived expression. Recipes (random_*, faker, etc.) pass through to ctx.recipe_eval."""
    if isinstance(node, dict) and len(node) == 1:
        key = next(iter(node))
        if key in EXPR_KEYS:
            return _OPS[key](node[key], ctx)
        # Delegate to recipe evaluator for random_*, faker, from, etc.
        if ctx.recipe_eval is not None:
            from app.mock.recipes import is_recipe

            if is_recipe(node):
                return ctx.recipe_eval(node, ctx)
    return node


def apply(response: dict, derived: list, ctx) -> dict:
    """Apply derived entries in order, mutating response."""
    for entry in derived:
        if "delete" in entry:
            _delete(response, entry["delete"])
            continue
        path = entry["path"]
        value = evaluate(entry["value"], ctx)
        _set(response, path, value)
    return response


# -- ops --


def _op_ref(arg: str, ctx) -> Any:
    return _get(ctx.root, arg)


def _op_sum(arg: list, ctx) -> float:
    return sum(_to_num(evaluate(x, ctx)) for x in arg)


def _op_sum_of(arg: str, ctx) -> float:
    container = _get(ctx.root, arg)
    if isinstance(container, dict):
        return sum(_to_num(v) for v in container.values())
    if isinstance(container, list):
        return sum(_to_num(v) for v in container)
    raise TypeError(f"sum_of expects dict or list at {arg}, got {type(container).__name__}")


def _op_sub(arg: list, ctx) -> float:
    if not arg:
        raise ValueError("sub requires at least one argument")
    values = [_to_num(evaluate(x, ctx)) for x in arg]
    result = values[0]
    for v in values[1:]:
        result -= v
    return result


def _op_mul(arg: list, ctx) -> float:
    result: float = 1
    for x in arg:
        result *= _to_num(evaluate(x, ctx))
    return result


def _op_div(arg: list, ctx) -> float:
    if len(arg) != 2:
        raise ValueError("div requires exactly 2 arguments")
    a = _to_num(evaluate(arg[0], ctx))
    b = _to_num(evaluate(arg[1], ctx))
    return a / b


def _op_round(arg: dict, ctx) -> float:
    value = _to_num(evaluate(arg["value"], ctx))
    digits = int(arg.get("digits", 0))
    return round(value, digits)


def _op_to_int(arg: Any, ctx) -> int:
    return int(_to_num(evaluate(arg, ctx)))


def _op_min(arg: list, ctx) -> Any:
    return min(evaluate(x, ctx) for x in arg)


def _op_max(arg: list, ctx) -> Any:
    return max(evaluate(x, ctx) for x in arg)


_OPS = {
    "ref": _op_ref,
    "sum": _op_sum,
    "sum_of": _op_sum_of,
    "sub": _op_sub,
    "mul": _op_mul,
    "div": _op_div,
    "round": _op_round,
    "to_int": _op_to_int,
    "min": _op_min,
    "max": _op_max,
}


# -- helpers --


def _to_num(v: Any) -> float:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    raise TypeError(f"expected number, got {type(v).__name__}: {v!r}")


def _split_pointer(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError(f"JSON Pointer must start with '/': {pointer!r}")
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]


def _get(root: Any, pointer: str) -> Any:
    cur = root
    for part in _split_pointer(pointer):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(f"pointer {pointer!r} not found (missing {part!r})")
            cur = cur[part]
        else:
            raise TypeError(f"cannot descend into {type(cur).__name__} at {pointer!r}")
    return cur


def _set(root: Any, pointer: str, value: Any) -> None:
    parts = _split_pointer(pointer)
    cur = root
    for part in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            if part not in cur:
                cur[part] = {}
            cur = cur[part]
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def _delete(root: Any, pointer: str) -> None:
    parts = _split_pointer(pointer)
    cur = root
    for part in parts[:-1]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur.get(part, {})
    last = parts[-1]
    if isinstance(cur, dict) and last in cur:
        del cur[last]
