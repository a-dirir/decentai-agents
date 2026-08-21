# DecentAI Agents

The agents DecentAI publishes. Nothing here ships inside the platform —
a deployment adds this repository as an **agent source**, reads what it
offers, and installs the agents it actually wants.

## Using it

In DecentAI, go to **AI → Marketplace**, add a source pointing at this
repository, and review what you would be approving. Reading the catalog
runs none of this code; approving an agent pins it to the exact commit
that was read.

## What is here

| Agent | What it does | Notable |
|---|---|---|
| `notebook` | Saves and finds notes, imports and exports notebook files | Every resource kind: a credential, records, files |
| `file_desk` | Lists, reads and saves documents in the platform's file store | File resources; read and change levels |
| `web_reader` | Fetches a public page and returns its text | One external function — the chat asks before it runs |
| `jira_ops` | Triages Jira work and prepares or sends COC HUB incident emails | Read/preview operations are safe; every Jira or email write asks first |

## The shape of a repository

```text
decentai-agents.yaml     # the catalog: what this repository offers
notebook/
  manifest.yaml          # what the agent declares
  agent.py               # the entrypoint class
  tools/                 # one module per tool
```

`decentai-agents.yaml` lists each agent with the folder it lives in. Paths
must stay inside the checkout, be unique, and be named for the agent's own
`agent.id`. A repository holding a single `manifest.yaml` at its root still
works — it is read as a catalog of one.

Each `manifest.yaml` declares the agent's tools, the permission level every
function needs, the credentials and records it defines, and the packages it
wants installed. That declaration is the whole of what an administrator
approves, and the runtime enforces it: a function that is not declared
cannot be called, and a level cannot be lowered by the code that runs.

## Permission levels

| Level | Meaning | Example here |
|---|---|---|
| 0 | read | `file_desk.file.list` |
| 1 | change | `file_desk.file.save` |
| 2 | sandboxed change | `notebook.archive.export` |
| 3 | external action | `web_reader.web.fetch` |

A chat runs functions at or below its own trust level and **asks** for
anything above it. That pause is the point.

## Writing your own

Copy a folder, change its `agent.id` and the folder name to match, and add
it to `decentai-agents.yaml`. The manifest reference is in the DecentAI
repository at `docs/agent-manifest.md`.
