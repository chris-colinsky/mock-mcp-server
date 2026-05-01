# Validation

Three tiers, **try them in this order**:

1. **OAS keywords** (`pattern`, `enum`, `minimum`, `format`, …). Standard, no code, work in any OAS-aware tool. Cover the majority of validation needs.
2. **Built-in custom validators** (`x-mock-validate` referencing entries in [`app/validators.py`](../app/validators.py)). For rules that JSON Schema can't express — typically anything that depends on the current time, the calling user, or external state.
3. **Writing your own** custom validator. Last resort; requires a Python function and a one-line registry add.

## Tier 1 — OAS keywords (preferred)

Standard JSON Schema / OAS keywords. The framework enforces these in `app/loader.py:_coerce` before any application code runs; failures become `422` with a structured `loc`/`msg`/`type` body.

### String validation

| Keyword     | Example                                            | Effect                                              |
|-------------|----------------------------------------------------|-----------------------------------------------------|
| `pattern`   | `pattern: '^\d{4}-\d{2}$'`                         | Regex match. PCRE-style, anchored explicitly with `^`/`$`. |
| `minLength` | `minLength: 3`                                     | Minimum string length.                              |
| `maxLength` | `maxLength: 64`                                    | Maximum string length.                              |
| `enum`      | `enum: [draft, review, published]`                 | Value must be one of the listed values.             |
| `format`    | `format: date-time` *(advisory unless code enforces)* | Hint for tooling; mock-mcp only enforces what `_coerce` checks. |

```yaml
parameters:
  - name: report_month
    in: query
    required: true
    schema:
      type: string
      pattern: '^\d{4}-\d{2}$'
```

### Numeric validation

| Keyword            | Example                  | Effect                                 |
|--------------------|--------------------------|----------------------------------------|
| `minimum`          | `minimum: 0`             | `>=` lower bound.                      |
| `maximum`          | `maximum: 100`           | `<=` upper bound.                      |
| `exclusiveMinimum` | `exclusiveMinimum: 0`    | `>` lower bound (no equals).           |
| `exclusiveMaximum` | `exclusiveMaximum: 100`  | `<` upper bound (no equals).           |
| `multipleOf`       | `multipleOf: 5`          | Value must be a multiple of N.         |

```yaml
parameters:
  - name: limit
    in: query
    schema:
      type: integer
      minimum: 1
      maximum: 1000
```

### When OAS keywords are enough

Most validation collapses to a combination of these. Examples that DON'T need a custom validator:

| Need                           | OAS keyword                                              |
|--------------------------------|----------------------------------------------------------|
| YYYY-MM-DD shape               | `pattern: '^\d{4}-\d{2}-\d{2}$'`                         |
| Currency code                  | `enum: [USD, EUR, GBP, JPY, …]`                          |
| Email shape                    | `pattern: '^[^@\s]+@[^@\s]+\.[^@\s]+$'` (or `format: email`) |
| Non-empty string               | `minLength: 1`                                           |
| Page size                      | `minimum: 1`, `maximum: 100`                             |
| ISO 4217-style 3-letter code   | `pattern: '^[A-Z]{3}$'`                                  |

If none of these get the job done, drop down to tier 2.

## Tier 2 — built-in custom validators

For rules JSON Schema can't express, reference a built-in validator from the operation's `x-mock-validate` block:

```yaml
x-mock-validate:
  - field: report_month
    type: past_month_utc
    message: "(optional override — only used if the validator's own message is empty)"
```

These run **after** the OAS schema check passes, before the response generator fires.

### Built-in catalog

| Name             | Rule                                                                                               |
|------------------|----------------------------------------------------------------------------------------------------|
| `past_month_utc` | Value must parse as `YYYY-MM` and be strictly before the current UTC month. Rejects future months and the current month. |

(That's the whole catalog right now. Adding the next built-in is intentionally easy; see Tier 3 below.)

### Why this needs code rather than YAML

`past_month_utc` depends on `datetime.now(UTC)` — it's not a property of the request value alone, so JSON Schema (which is purely declarative) can't express it. Anything that references **runtime state** (current time, environment, calling user) needs to live in code. Pure shape/range checks belong in tier 1.

### Error message handling

When a validator raises `ValueError(...)`, the framework returns 422 with the exception's own message in the response body. The `message:` field in the YAML is a *fallback* — used only when the exception didn't carry a message. Most built-in validators raise specific messages, so the YAML override is decorative. Keep it for documentation purposes if you like; it's harmless.

## Tier 3 — writing your own custom validator

Last resort. Requires editing the framework source.

### Steps

1. **Add a function** to `app/validators.py`. Signature: takes the resolved value, raises `ValueError(...)` with a clear message on failure, returns nothing on success.

   ```python
   def _is_past_business_day(value: Any) -> None:
       """Value must parse as YYYY-MM-DD and be a past weekday in UTC."""
       if not isinstance(value, str):
           raise ValueError("expected YYYY-MM-DD string")
       try:
           d = datetime.strptime(value, "%Y-%m-%d")
       except ValueError as exc:
           raise ValueError("must be a valid YYYY-MM-DD date") from exc
       now = datetime.now(UTC).date()
       if d.date() >= now:
           raise ValueError("must be a past date (today and future are not allowed)")
       if d.weekday() >= 5:
           raise ValueError("must be a weekday (Mon–Fri)")
   ```

2. **Register it** in the `VALIDATORS` dict at the bottom of the same file:

   ```python
   VALIDATORS: dict[str, Callable[[Any], None]] = {
       "past_month_utc": _past_month_utc,
       "past_business_day_utc": _is_past_business_day,
   }
   ```

3. **Reference it** from any profile:

   ```yaml
   x-mock-validate:
     - field: report_date
       type: past_business_day_utc
   ```

4. **Document it** — add a row to the [Built-in catalog](#built-in-catalog) table above.

5. **Test it** — `tests/test_validators.py` parametrizes over the registry; add cases for accept and reject.

### Why this is a known limitation

Today, adding a validator means a code change to `app/validators.py`. That's fine for a developer-authored project where the same person who writes profiles also writes Python, but it doesn't scale to a UI where non-developers create profiles.

Future directions tracked in [FUTURE.md](FUTURE.md):

- A **larger built-in catalog** — if the framework ships generous built-ins for common patterns (date ranges, currencies, business-day rules, country codes), most profiles never need to escape tier 2.
- A **predicate DSL inside YAML** that composes the existing operators (`ref`, `sum`, comparators, regex match) into boolean checks — author-time validation without code.

Both are open design questions; nothing is committed.

## Validation flow at a glance

```
incoming request
       │
       ▼
 ┌─────────────────────────┐
 │ Tier 1: OAS keywords    │  (pattern, enum, minimum, …) → 422 on fail
 │  enforced in _coerce    │
 └─────────────────────────┘
       │ pass
       ▼
 ┌─────────────────────────┐
 │ Tier 2 + 3:             │  registered validators (past_month_utc, …)
 │  x-mock-validate hooks  │  → 422 on fail (validator's own message wins)
 └─────────────────────────┘
       │ pass
       ▼
   x-mock-dynamic / x-mock-static
       │
       ▼
   200 response
```
