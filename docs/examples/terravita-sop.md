# Example: terravita-sop

[`configs/terravita-sop.yaml`](../../configs/terravita-sop.yaml)

Mock of the [Terravita Sales & Operations Planning API](https://github.com/chris-colinsky/deterministic-ai-agent-pattern). The real backend reads a sales CSV → calculates supply-chain metrics with Pandas → asks an LLM for an executive narrative. This profile returns plausible synthetic data with the same response shape so an agent can be evaluated without an LLM round-trip.

## Endpoint

`GET /api/v1/generate-sop`

No request parameters. Returns the full `SOPResponse`:

- `status: "success"`
- `metrics: SOPMetrics` — `total_m4_revenue`, `skus_at_risk`
- `red_flag_data: list[RedFlagItem]` — at-risk SKUs with cover, reorder qty, and revenue
- `llm_briefing: str` — markdown narrative

## Run + hit it

```bash
uv run mock-mcp --config terravita-sop
curl -H "Authorization: Bearer mock-test-token" \
  "http://localhost:8002/api/v1/generate-sop"
```

## What this profile demonstrates

- **Variable-shape responses with arrays** — fixed-length list of 4 SKU records. Each item declared explicitly, so each can have its own recipe combination. (See the open `random_list` recipe idea in [FUTURE.md](../FUTURE.md) for variable-length lists.)
- **`template` rendering inside `derived`** — the LLM briefing pulls computed metric values via `{ref: /metrics/...}`, which only resolve after the response walk completes. Living in `derived` (not `response`) is what makes it work.
- **Faker for SKU identifiers** — `template` + `faker.pyint` to generate `TV-NNN-DRY` / `TV-NNN-RFR` / `TV-NNN-CHL`-shaped IDs.
- **No `seed_from`** — matches the real LLM endpoint's per-call variance. Add `seed_from: query.seed` plus a corresponding query parameter if you want reproducible output for snapshot testing.
- **No CSV download endpoint** — the real backend has a second route (`/api/v1/download-pos`) that streams a CSV. Deliberately not mocked: file downloads don't fit MCP's content-block model. A proper MCP-shaped equivalent would be a `get_pending_purchase_orders` tool returning the rows as JSON.

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

## Connecting to the real Terravita backend

If you have the real backend running locally and want to A/B against the mock, point Forbin at both via separate environments:

```
[forbin profiles]
terravita/
  mock          → http://localhost:8002/mcp  (mock-test-token)
  local-real    → http://localhost:8000/mcp  (your real token)
  prod          → https://terravita.example.com/mcp (prod token)
```

Press `p` mid-session to switch and re-run the same tool. Diff the responses to spot drift between mock and real.
