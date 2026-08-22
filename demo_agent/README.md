# Demo Agent

This is the canonical DecentAI schema-v1 example. It uses a small notebook
workflow so every configuration pattern is concrete, but its real purpose is
to be copied, read, and modified when building another agent.

## What it demonstrates

| Area | Where to look |
|---|---|
| Agent identity, instructions, tags, and step limit | `manifest.yaml` → `agent` |
| Entrypoint and dependencies | `manifest.yaml` → `implementation` |
| Required and optional authorization scopes | `note.save` and `note.find` |
| Scope normalization | `authorization.scopes.notebook` |
| Secrets and protected fields | `resources.secrets.connection` |
| Single and multiple data bindings | `settings` and `note` |
| File types and size constraints | `resources.files.document` |
| Exact resource operations | Each function's `resources` block |
| Permission levels 0–3 | `find`, `save`, `export`, and `push` |
| JSON Schema inputs and outputs | Every function |
| Platform resource references | `note_ref`, `file_ref`, and `note_refs` |
| Progress messages and success/error results | Files under `tools/` |

The simulated sync functions consume a real bound secret but never make a
network request. This keeps the example safe and deterministic.

## Copy it to create an agent

1. Copy this directory and give the copy a lowercase, stable id such as
   `customer_lookup`.
2. Change the directory name, `agent.id`, and the catalog entry to that same
   id.
3. Rename `DemoAgent` and update `implementation.entrypoint` to match.
4. Replace the example resources with only the secrets, data, and files your
   agent genuinely needs.
5. Replace the tools and functions. Keep every function's resource operations
   and permission level as narrow as possible.
6. Update the agent instructions so the model knows when to use the tools and
   what it must never assume.
7. Add tests for loading, resource access, validation failures, and external
   actions.

## Code contract

`agent.py` returns `ToolBase` instances from `tools()`. A tool's `id` must
match its manifest tool id. Each async method implements a function with the
same id; a Python keyword such as `import` uses a trailing underscore
(`import_`). A method returns `(payload, "success")` or `(payload, "error")`.

All persistent state goes through `call.resources`. Agents must not read
arbitrary host paths, embed credentials, or keep deployment state in module
globals.

## Before publishing

- Confirm the catalog id, directory name, and `agent.id` match.
- Declare every callable function and implement every declared function.
- Use opaque `x-resource` references instead of accepting database ids or
  filesystem paths.
- Store tokens and passwords as secret `values`, never readable `keys`.
- Treat network calls and third-party writes as permission level 3.
- Bound input sizes, result counts, timeouts, and dependency versions.
- Run the repository tests from an environment where DecentAI's `ai_runtime`
  package is importable.
