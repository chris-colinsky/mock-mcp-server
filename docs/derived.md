# Derived DSL

Use `derived:` (under `x-mock-dynamic`) for cross-field invariants — anything that needs to read other generated values. Each entry is `{path: <json-pointer>, value: <expression>}` (or `{delete: <json-pointer>}`). Entries are applied **in order**, so later entries can reference values written by earlier ones.

Recipe verbs (`random_int`, `from`, `faker`, …) are also valid expressions, so you can mix RNG draws with computed expressions naturally.

## Operators

| Op           | Example                                         | Result                                              |
|--------------|-------------------------------------------------|-----------------------------------------------------|
| `ref`        | `{ ref: /summary_stats/total }`                 | Look up a value by JSON Pointer.                    |
| `sum`        | `{ sum: [1, 2, { ref: /a }] }`                  | Sum of arguments.                                   |
| `sum_of`     | `{ sum_of: /summary_stats/by_platform }`        | Sum of all values in a dict or list.                |
| `sub`        | `{ sub: [10, 3, 1] }` → 6                       | Subtract subsequent args from the first.            |
| `mul`        | `{ mul: [{ ref: /price }, 1.08] }`              | Product.                                            |
| `div`        | `{ div: [{ ref: /total }, 4] }`                 | Division (exactly two args).                        |
| `round`      | `{ round: { value: <expr>, digits: 2 } }`       | Round to N digits.                                  |
| `to_int`     | `{ to_int: { mul: [{ ref: /n }, 0.5] } }`       | Coerce to int (truncates).                          |
| `min`/`max`  | `{ min: [{ ref: /a }, 100] }`                   | Min/max of evaluated arguments.                     |
| `delete`     | `{ delete: /scratch }`                          | (Action — top-level entry, not a value expression.) |

## JSON Pointer paths

Standard RFC 6901: `/foo/bar`, `/list/0/key`. Escape `/` with `~1`, `~` with `~0`.

Examples:

| Pointer                                | Resolves to                              |
|----------------------------------------|------------------------------------------|
| `/metrics/total`                       | `response["metrics"]["total"]`           |
| `/red_flag_data/0/SKU`                 | `response["red_flag_data"][0]["SKU"]`    |
| `/summary_stats/brands_by_platform`    | the entire dict                          |

## Common patterns

**Sum invariant** (computed total = sum of parts):

```yaml
response:
  counts:
    a: { random_int: [10, 50] }
    b: { random_int: [10, 50] }
    c: { random_int: [10, 50] }
  total: { static: 0 }     # placeholder

derived:
  - path: /total
    value: { sum_of: /counts }
```

**Derived ratio + remainder**:

```yaml
derived:
  - path: /adjusted
    value:
      round:
        digits: 2
        value:
          mul:
            - { ref: /raw }
            - { sub: [1, { random_float: [0.01, 0.05] }] }
  - path: /delta
    value:
      sub:
        - { ref: /raw }
        - { ref: /adjusted }
```

**Bounded random with cross-field reference**:

```yaml
- path: /done_count
  value:
    random_int:
      - 5
      - { to_int: { mul: [{ ref: /total }, 0.2] } }
```

**Cleanup with `delete`** (remove a scratch field used only as an intermediate):

```yaml
- delete: /scratch
```

**Template inside derived** (string interpolation that pulls computed values):

```yaml
- path: /llm_briefing
  value:
    template:
      format: "Total revenue ${total} across {n} SKUs."
      vars:
        total: { ref: /metrics/total_m4_revenue }
        n:     { ref: /metrics/skus_at_risk }
```

This is the canonical use case for `template` in `derived`: the response walk has finished, so `ref` can read populated values.

## Evaluation order, in detail

Inside `x-mock-dynamic`:

1. **`response:` walk** (top-down, declared order).
   - Each leaf recipe is evaluated; results land in the response tree.
   - During the walk, `ctx.root` (what `ref` resolves against) is **empty** — the response isn't built yet.
   - Recipes can read request data via `from`, but cannot reference other in-progress fields.
2. **`derived:` apply** (top-down, declared order).
   - Each entry's `value` expression is evaluated, then written to `path`.
   - `ctx.root` now points at the completed response from step 1, so `ref` works.
   - Earlier derived entries are visible to later ones.

If you need a derived field A that depends on derived field B, declare B first.

## See also

- [Recipes](recipes.md) — leaf-recipe catalog. All recipes work as expressions inside derived values.
- [Validation](validation.md) — for request-side validation rules.
- [Examples](examples/) — worked profiles using these patterns.
