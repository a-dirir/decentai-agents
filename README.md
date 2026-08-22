# DecentAI Agents

Reference agents and a complete development template for DecentAI.

Use this repository in either of two ways:

- Add it to DecentAI as an agent source and install an offered agent.
- Copy `demo_agent/` to build an agent that integrates your own system.

DecentAI reads the catalog and manifests before running any agent code. An
administrator can inspect the declared dependencies, tools, permissions,
authorization scopes, secrets, data, and files before approving an exact
repository commit.

## Repository contents

| Directory | Purpose |
|---|---|
| [`demo_agent/`](demo_agent/) | Canonical schema-v1 template covering scopes, secrets, data, files, resource references, and permission levels 0–3 |
| [`file_desk/`](file_desk/) | Small example using DecentAI's managed file store |
| [`web_reader/`](web_reader/) | Small example of a dependency and an external network action |
| [`tests/`](tests/) | Loader, resource, validation, and security-focused tests |
| [`decentai-agents.yaml`](decentai-agents.yaml) | Repository catalog read by DecentAI |

## Install an agent

1. In DecentAI, open **AI → Marketplace**.
2. Add this Git repository as an agent source.
3. Review the catalog and the selected agent's manifest.
4. Approve the agent and its declared resources and permissions.

Reading a source does not execute its Python code. Approval pins the agent to
the commit that was reviewed.

## Create an agent

Start from the complete demo:

```text
decentai-agents.yaml
your_agent/
  manifest.yaml
  agent.py
  README.md
  tools/
    __init__.py
    your_tool.py
tests/
```

Then:

1. Copy `demo_agent/` to a directory named for your agent.
2. Use the same lowercase id in the directory name, catalog entry, and
   `agent.id`.
3. Replace the demo's resources and functions with the minimum your
   integration requires.
4. Implement each manifest tool with an `AgentBase`/`ToolBase` class.
5. Add tests and run the loader before publishing.

The detailed mapping and checklist are in
[`demo_agent/README.md`](demo_agent/README.md). The commented
[`demo_agent/manifest.yaml`](demo_agent/manifest.yaml) is the primary template.

## Ask a coding agent to build one

Codex, Claude Code, and similar coding agents can use the repository itself as
the specification. A useful starting prompt is:

```text
Create a DecentAI agent named <agent_id> in this repository.

First read README.md, demo_agent/README.md, demo_agent/manifest.yaml,
demo_agent/agent.py, its tools, and tests/test_agents.py. Follow their existing
schema and SDK patterns. Add the new agent to decentai-agents.yaml. Give each
function the narrowest resources, authorization scopes, and permission level
that its behavior requires. Never embed credentials or accept host filesystem
paths. Add focused tests and report any assumptions about the external API.

The agent should: <describe the integration and operations here>.
```

## Repository contract

`decentai-agents.yaml` contains only catalog metadata and agent ids/paths. Each
path must remain inside the checkout and contain a `manifest.yaml`. The catalog
id, directory name, and manifest `agent.id` must agree.

The manifest is the approval and enforcement boundary. It declares:

- Agent identity, instructions, execution limits, entrypoint, and dependencies
- Tools and functions with JSON Schema inputs and outputs
- A permission level and timeout for every function
- Exact secret, data, and file operations available to every function
- Authorization actions and optional scoped grants
- Installation-time resource definitions and bindings

Code cannot safely widen this declaration: a function or resource operation
that is not declared should be rejected by the runtime.

## Permissions

| Level | Meaning | Example |
|---:|---|---|
| 0 | Read-only or observational | Find saved demo notes |
| 1 | A platform data change | Save a demo note |
| 2 | A sandboxed/platform-contained change | Import or export a managed document |
| 3 | An external action | Fetch a public page or push to a remote service |

A chat can run functions at or below its trust level. A function above that
level pauses for approval. Choose the level based on the action's effect, not
how harmless the implementation appears during development.

## Resources and secrets

Agents access deployment state through `call.resources`:

- **Secrets** hold connection details and credentials. Passwords and tokens
  belong in write-only `values`, never readable `keys`.
- **Data** holds structured platform records. Functions receive only the
  operations declared in their manifest.
- **Files** are managed platform objects. Agents should accept opaque file
  references, not arbitrary host paths.

Use `x-resource` in input and output schemas for resource references. This
lets the runtime validate ownership and resource type instead of trusting a
raw identifier supplied by code or a model.

## Authorization scopes

Scopes restrict an action to a normalized value such as a notebook, tenant,
project, or issue. A function maps a validated input to a declared scope:

```yaml
authorization:
  action: note.save
  scopes:
    notebook: {from_input: notebook}
```

The demo includes required scopes, optional scopes, normalization, and actions
without scopes.

## Development and testing

The tests require a Python environment in which DecentAI's `ai_runtime`
package is importable, plus the dependencies used by the catalog agents.

```bash
python -m pytest -q
```

Before publishing, verify that:

- Every catalog agent loads without manifest errors.
- Every declared function has an implementation.
- Inputs fail closed when references or values are invalid.
- Resource access is limited to declared operations.
- External calls cannot reach unintended private destinations.
- Dependencies are necessary and version-bounded.
- No credentials, local configuration, caches, or generated files are tracked.

## Design principles

- Declare the smallest useful capability.
- Keep credentials and persistence behind mediated resources.
- Make writes explicit and external effects consentable.
- Validate complete inputs before making partial changes.
- Return verified results; never imply an external action succeeded before
  checking its outcome.
- Keep examples small enough for a human or coding agent to audit quickly.
