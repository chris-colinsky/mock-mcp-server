# Recipe catalog

Recipes live inside `x-mock-dynamic.response`. A **recipe** is a one-key dict whose key is one of the verbs below. Anywhere a recipe appears in the response tree, it's evaluated; everything else is left alone (literals pass through). Recipes can sit at the top level, inside dicts, or inside lists.

The walk is **top-down, declared order**. RNG draws happen in that order, which matters if you care about reproducing a specific sequence.

For derived expressions (`ref`, `sum`, etc.) used alongside recipes, see [derived.md](derived.md).

## `static` — literal value

```yaml
success: { static: true }
message: { static: "Generated successfully" }
empty:   { static: [] }
```

Anything passes — strings, numbers, booleans, lists, dicts, `null`. The value is returned verbatim, no recipe walking inside it.

## `random_int: [low, high]` — uniform integer (inclusive)

```yaml
total_items: { random_int: [10, 100] }
```

Bounds may be derived expressions, evaluated lazily:

```yaml
done_count:
  random_int:
    - 5
    - { to_int: { mul: [{ ref: /summary_stats/total_brands }, 0.2] } }
```

When `seed_from` is set, this draw is deterministic for a given input.

## `random_float` — uniform float

Two forms:

```yaml
# raw uniform
delta_pct: { random_float: [0.001, 0.01] }

# uniform + rounding
total_earnings:
  random_float:
    range: [200000, 500000]
    round: 2
```

`round` is applied after the draw; bounds may be derived expressions.

## `random_choice: [...]` — pick one

```yaml
status:   { random_choice: [pending, complete, errored] }
priority: { random_choice: [1, 2, 3, 5, 8] }
```

Each item is returned as-is (recipes inside the list are NOT evaluated — wrap with a derived expression if you need that).

## `faker` — call a [Faker](https://faker.readthedocs.io/) provider

```yaml
# short form: provider name
name:       { faker: company.name }
email:      { faker: email }
ip_address: { faker: ipv4 }

# long form: with args/kwargs
big_number:
  faker:
    provider: pyint
    kwargs:  { min_value: 1000, max_value: 999999 }
```

When `seed_from` is set, Faker is seeded with the same hash so its output is deterministic across processes.

The full Faker provider catalog is at <https://faker.readthedocs.io/en/master/providers.html>. Common ones:

- `name`, `first_name`, `last_name`
- `email`, `safe_email`
- `address`, `city`, `country`, `country_code`
- `company`, `company_email`, `bs`
- `phone_number`, `ipv4`, `ipv6`, `mac_address`, `user_agent`
- `pyint`, `pyfloat`, `pystr`, `pybool`
- `date`, `date_this_year`, `date_of_birth`, `time`
- `uuid4`, `sha256`

## `from` — pull a value from the request

```yaml
# short form
report_month: { from: query.report_month }

# long form with map (translates request value via a lookup table)
environment:
  from:
    path: query.use_preview_db
    map: { true: preview, false: prod }

# long form with slicing (works on string values)
year_part:
  from: { path: query.report_month, slice: [0, 4] }    # "2025-06" → "2025"

# long form with split-and-index
month_part:
  from: { path: query.report_month, split: '-', index: 1 }   # "2025-06" → "06"
```

Paths: `query.<name>` for query parameters, `path.<name>` for path parameters. `slice` and `split` operate on strings; combine with `map` to transform-then-map.

## `now` — current ISO-8601 UTC timestamp

```yaml
generated_at: { now: true }
```

The one intentionally non-deterministic recipe. Use for fields like "generated at" or "current time" where freshness is the point.

## `template` — Python `str.format` interpolation

```yaml
output_file_path:
  template:
    format: "s3://bucket/year={year}/month={month}/data.csv"
    vars:
      year:  { from: { path: query.report_month, split: '-', index: 0 } }
      month: { from: { path: query.report_month, split: '-', index: 1 } }
```

Var values may be recipes (`from`, `faker`, `now`, `random_*`) **or** derived expressions (`ref`, `sum`, etc.). They're evaluated first; the resolved values are then substituted into `format`.

### Placement rule

Templates that only reference `query`/`path` or generate fresh values can sit anywhere in the response tree. Templates that use `{ref: /path/to/field}` to pull other generated fields must go in `derived` (not `response`), because `ref` resolves against the *completed* response — and during the initial response walk, that completed response doesn't exist yet.

See [`configs/terravita-sop.yaml`](../configs/terravita-sop.yaml) for a worked example: the LLM briefing's metric placeholders are rendered in `derived` after `metrics` is populated.

## Recipe + derived composition

Recipe arguments that look like derived expressions (e.g. `{ref: /...}` inside `random_int` bounds) are auto-resolved through the derived evaluator. The reverse is also true — a recipe inside a derived expression is invoked through the recipe evaluator. This means `random_int`, `faker`, etc. all work seamlessly inside `derived` entries.

See [derived.md](derived.md) for the full operator catalog.
