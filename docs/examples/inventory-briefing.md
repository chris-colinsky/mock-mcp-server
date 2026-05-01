# Example: inventory-briefing

[`configs/inventory-briefing.yaml`](../../configs/inventory-briefing.yaml)

Stand-in for a Sales & Operations Planning briefing endpoint. The kind of real backend this might mirror reads sales data → calculates supply-chain metrics with Pandas → asks an LLM for an executive narrative. This profile returns plausible synthetic data with the same response shape so an agent can be evaluated without the LLM round-trip.

## Endpoint

`GET /api/v1/generate-sop`

No request parameters. Returns the full `SOPResponse`:

- `status: "success"`
- `metrics: SOPMetrics` — `total_m4_revenue`, `skus_at_risk`
- `red_flag_data: list[RedFlagItem]` — at-risk SKUs with cover, reorder qty, and revenue
- `llm_briefing: str` — markdown narrative

## Run + hit it

This profile is **unauthenticated** — no bearer token required:

```bash
uv run mock-mcp --config inventory-briefing
curl "http://localhost:8002/api/v1/generate-sop"
```

## What this profile demonstrates

- **Variable-shape responses with arrays** — fixed-length list of 4 SKU records. Each item declared explicitly, so each can have its own recipe combination. (See the open `random_list` recipe idea in [FUTURE.md](../FUTURE.md) for variable-length lists.)
- **`template` rendering inside `derived`** — the LLM briefing pulls computed metric values via `{ref: /metrics/...}`, which only resolve after the response walk completes. Living in `derived` (not `response`) is what makes it work.
- **Faker for SKU identifiers** — `template` + `faker.pyint` to generate `SKU-NNN-DRY` / `SKU-NNN-RFR` / `SKU-NNN-CHL`-shaped IDs (Dry / Refrigerated / Chilled product classes — common in food / pharma / cold-chain inventory).
- **Unauthenticated mode** — no `x-mock-auth` block at the root, so the server is open. Compare with the `monthly-report` profile to see the bearer-auth pattern. See [auth.md](../auth.md) for full coverage.
- **No `seed_from`** — matches a backend whose real implementation is non-deterministic (LLM calls produce fresh narratives on every request). Add `seed_from: query.seed` plus a corresponding query parameter if you want reproducible output for snapshot testing.

## The template-in-derived pattern

This profile's most interesting trick. Standard placement of `llm_briefing` in `response`:

```yaml
# DOESN'T WORK — ctx.root is empty during the response walk
response:
  metrics:
    total_m4_revenue: { random_float: { range: [180000, 320000], round: 2 } }
    skus_at_risk: { static: 4 }
  llm_briefing:
    template:
      format: "Total revenue ${total} with {at_risk} at-risk SKUs."
      vars:
        total:   { ref: /metrics/total_m4_revenue }   # ← undefined here
        at_risk: { ref: /metrics/skus_at_risk }       # ← undefined here
```

Move the template to `derived`:

```yaml
response:
  metrics:
    total_m4_revenue: { random_float: { range: [180000, 320000], round: 2 } }
    skus_at_risk: { static: 4 }
  llm_briefing: { static: "" }   # placeholder

derived:
  - path: /llm_briefing
    value:
      template:
        format: "Total revenue ${total} with {at_risk} at-risk SKUs."
        vars:
          total:   { ref: /metrics/total_m4_revenue }    # ← now resolves
          at_risk: { ref: /metrics/skus_at_risk }
```

By the time `derived` runs, the response tree is built and `ref` works.

## Comparing mock vs. real with Forbin

If you have a real S&OP backend running locally and want to A/B against the mock, point [Forbin](../pairing-with-forbin.md) at both via separate environments:

```
[forbin profiles]
sop/
  mock          → http://localhost:8002/mcp        (no token)
  local-real    → http://localhost:8000/mcp        (your real token)
  prod          → https://your-server.example.com/mcp (prod token)
```

Press `p` mid-session to switch and re-run the same tool. Diff the responses to spot drift between mock and real.
