# IDE setup

Profiles ship with a `# yaml-language-server: $schema=../schemas/mock-mcp-config.schema.json` directive at the top of the file. Configured editors use it to validate the `x-mock-*` extensions and autocomplete known properties as you type.

## VS Code

Install the [YAML extension by Red Hat](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml). The `$schema` directive is honored automatically — no settings changes needed.

After install, opening any file under `configs/` will show:

- Inline completions for `x-mock-port`, `x-mock-auth`, `x-mock-mcp`, etc.
- Hover docs on each property.
- Squiggles on unknown keys, missing required fields, and bad shapes.

## PyCharm / IntelliJ

The `# yaml-language-server:` directive isn't auto-honored, but you can wire the schema up explicitly:

1. **Settings** → **Languages & Frameworks** → **Schemas and DTDs** → **JSON Schema Mappings**.
2. Click **+** to add a new mapping:
   - **Schema file or URL:** `schemas/mock-mcp-config.schema.json` (relative to project root)
   - **Schema version:** Draft 7
   - **File path pattern:** `configs/*.yaml`
3. Apply.

You'll get the same completions and warnings VS Code does.

## Other editors

Any editor with [yaml-language-server](https://github.com/redhat-developer/yaml-language-server) support (Neovim with `coc-yaml` or `nvim-lspconfig`, Helix, Sublime, Zed, …) honors the `$schema` directive automatically. Install the language server, open the YAML, validation just works.

## What you'll catch

Once configured, typos like `sx-mock-dynamic` and unknown properties show up as warnings before you commit:

```
sx-mock-dynamic:
^^^^^^^^^^^^^^^^
Property is not allowed.
```

```yaml
x-mock-auth:
  type: bearer
  toekn_env: BEARER_TOKEN     # ← warning: not in schema
```

## Limits of schema validation

Some constraints are application-level, not schema-level — these still need `make validate-configs` to catch:

- "Exactly one of `x-mock-static` or `x-mock-dynamic` per operation" — the schema doesn't enforce mutual exclusion (allows both, allows neither). The loader does.
- JSON Pointer references inside `derived` (e.g. `{ref: /summary_stats/total}`) — the schema doesn't know whether the path resolves; you find out at runtime or by running validate-configs.
- `seed_from: query.X` — the schema doesn't verify that `X` is a declared query parameter.

So: editor schema gets you syntax + shape; `make validate-configs` (and the test suite) gets you semantics.
