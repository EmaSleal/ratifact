# ratifact

A local [MCP](https://modelcontextprotocol.io) server that turns each repository into the persistent memory of its
project. Decisions (ADRs), open items, code tasks and session logs live as Markdown files in a git repository of their
own, outside the code repository, so no branch or checkout ever changes them. Any MCP client (Claude Desktop, Claude
Code, Pi, Codex) reads and writes the same memory through 28 tools.

- **Decisions are ratified, not assumed.** Every decision is recorded as `proposed`; it only becomes `accepted` through
  `accept_decision`, with the user's literal words, and the client asks the user to approve that call.
- **Tasks travel from the chat to the coding agent.** A change agreed in a chat is recorded with `create_task`; the
  coding agent runs it with `/run-task T-NNN` (`$run-task T-NNN` in Codex), on its own branch, and leaves the result
  for review.
- **Everything is plain files under git.** Views such as `DECISIONS.md` and `OPEN.md` are regenerated from the
  records; nothing is deleted, only changes status.

Linux and macOS (Windows through WSL). Python 3.10 or newer. Spanish documentation: [LEEME.md](LEEME.md).

## Install

```
uv tool install ratifact      # fixed installation: ~/.local/bin/ratifact
ratifact install              # shows the plan: which clients it found and what it would change
ratifact install --apply      # does it, with a backup of every file it touches
```

`ratifact install` configures every client it finds, so you never edit their JSON/TOML by hand:

| Client | Where |
|---|---|
| Claude Desktop | `~/.config/Claude/claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`) |
| Claude Code | `claude mcp add --scope user` (or `~/.claude.json` if the `claude` command is not installed) |
| Pi | `~/.pi/agent/mcp.json` |
| Codex | `~/.codex/config.toml` |

Each one ends with a server named `ratifact` that runs `<absolute path>/ratifact serve`, with no environment variables.
Other servers and settings are kept identical. Before writing, the file is backed up as `<file>.bak-ratifact-<date>`
next to it (files inside a project — `CLAUDE.md`, `AGENTS.md`, `.claude/settings.json` — are backed up instead under
`~/.local/state/ratifact/backups/<date>/<absolute path>`, so nothing is added to your repositories; a file that is not
rewritten gets no backup), the new content is validated by parsing it again, and the original is replaced atomically; an invalid file is
reported and left untouched. A client that is not installed is skipped; `--client claude-desktop|claude-code|pi|codex`
limits the run to one. A second `--apply` changes nothing and says so. Restart the clients afterwards.

`uvx ratifact …` works for one-off commands (`uvx ratifact doctor`), but clients need a fixed installation:
`ratifact install` refuses to point them at the temporary copy that `uvx` runs.

From a clone instead of PyPI: `uv tool install <path to the clone>` (after each update:
`uv tool install --reinstall <path>` and restart the clients).

## First project

With no configuration, `ratifact install --apply` creates an empty `~/.config/ratifact/projects.json`. Then, in any
chat with the server connected, ask:

> register the project my-app with the code in ~/Projects/my-app

`register_project` adds it to `projects.json`, creates its memory (by default `~/Projects/.ratifact/my-app`, a git
repository of its own), detects the test command and returns two texts to paste:

1. the **Claude project instructions** (Claude Desktop / claude.ai project → *Project instructions*);
2. the block for the repository's `CLAUDE.md` (Claude Code) and `AGENTS.md` (Pi, Codex), which starts with
   ``This repository uses the `ratifact` MCP server with project `my-app`.``

`project_instructions("my-app")` returns them again at any time. The projects folder is `~/Projects` unless
`RATIFACT_BASE` says otherwise; `RATIFACT_CONFIG` and `RATIFACT_LOG` override the configuration and the usage log.

## /run-task

`ratifact install --apply` links the `run-task` skill from the installed package:

- Claude Code: `~/.claude/commands/run-task.md`
- Pi: `~/.pi/agent/prompts/run-task.md` (and `~/.pi/agent/skills/run-task` if that folder exists)
- Codex: `~/.codex/skills/run-task` and `~/.agents/skills/run-task` (the whole folder: Codex does not follow a linked
  `SKILL.md`)

In the repository, `/run-task T-007` (Codex: `$run-task T-007`) reads the task with `read_task`, creates its branch
from main, implements it, runs the project's tests and leaves the task `in_review` (or `failed`) with the result. The
deprecated `/tarea` alias keeps working until 1.1. A link that exists as a real file or folder is never replaced: the
plan says to remove it by hand. The links point inside the installed package; if a reinstall moves it (for example
`uv tool install --reinstall` with another Python version), `ratifact doctor` reports the links as pending and
`ratifact install --apply` fixes them.

## Commands

| Command | What it does |
|---|---|
| `ratifact serve` | The MCP server over stdio (what the clients launch). |
| `ratifact install [--apply] [--client NAME]` | Configures the MCP clients and links /run-task (plan unless `--apply`). |
| `ratifact doctor` | Read-only diagnosis: version and where it runs from, configuration, each project's code, memory, schema and git status, integrations, the state of each client (configured with ratifact / old configuration / not configured / not found) and the pending actions. Exit code 1 if something is pending. |
| `ratifact upgrade [--apply]` | One-time upgrade from memoria-proyectos (below). |
| `ratifact report [--days N] [--project P] [--log PATH]` | Usage summary from the local telemetry log (`~/.local/state/ratifact/uso.jsonl`: tool, size, duration and error of each call — never content). |
| `ratifact --version` | Installed version. |

## Integrations

Optional integrations add conditional guidance to `get_context`, `create_task` and `update_task`; ratifact never
calls another MCP server.

| Integration | Detected by | Role |
|---|---|---|
| codegraph | a `.codegraph/` folder in the project | code structure for planning and checking a task's scope |
| gentle-ai | a `.atl/` folder in the project | the task runs as its delegated-direct route (never SDD), is its ODD feature document, and RDD (if on) reviews it before `in_review` |
| engram | never detected | its guidance is conditional ("if you have it") |

The default is `auto` (used when detected). `ratifact install` reports what it detected per project and never asks.
To turn one off: `update_project("my-app", integrations="codegraph=off")` (`=auto` turns it back on).

## Model routing

You choose which model each delegated role uses (`explore`, `write`, `verify`), independent of any integration. The
global value lives in `settings.json`, next to the active `projects.json` (e.g. `~/.config/ratifact/settings.json`);
you create it by hand (`ratifact install` never writes it):

```json
{"models": {"explore": "haiku", "write": "sonnet", "verify": "sonnet"}}
```

Per-project exceptions: `update_project("my-app", models="explore=haiku,write=sonnet")` stores `"models"` in that
project's entry of `projects.json`; they win role by role and the other roles inherit the global value.
`models="write=inherit"` removes the project's exception for that role. Unknown roles and empty values are rejected
with the list of valid roles. Model names are free text for your client (aliases or full ids).

When at least one role is set, `update_task(..., "in_progress")` adds a "Model routing" block (each role, its model
and whether it comes from `global` or `project`): it is your explicit request to set that model when the agent
delegates the role; a client that cannot choose a sub-agent's model ignores it, and roles without a model use the
session's model. With no configuration the response is unchanged. An invalid `settings.json` never breaks a tool
(it is ignored with a warning in that block); `ratifact doctor` reports it without changing it and shows each
project's effective models (or `models: session default`).

## Upgrade from memoria-proyectos

ratifact was called memoria-proyectos before 1.0. With every client closed:

```
uv tool install ratifact
ratifact upgrade              # plan: nothing changes
ratifact upgrade --apply      # memories to .ratifact/, projects.json to English keys, with backups
ratifact install --apply      # server key memoria-proyectos → ratifact in every client
ratifact doctor               # should end with "Pending actions: none"
```

`ratifact install` replaces the `memoria-proyectos` entry with `ratifact` (never both), renames the Claude Code
permissions `mcp__memoria-proyectos__<tool>` → `mcp__ratifact__<tool>` in `~/.claude/settings.json` and in the
`.claude/settings.json` of each registered project, moves Codex per-tool approval tables to the new key, and rewrites
the generated `CLAUDE.md`/`AGENTS.md` block (only that exact text). It lists what it cannot change: Claude Desktop
keeps tool approvals per server name, so mark `propose_decision`, `add_pending`, `create_task`, `create_document`,
`register_project`, `accept_decision` and `accept_decisions` as *requires approval* again. If the default
configuration does not exist but a server still runs with `MEMORIA_PROYECTOS_CONFIG`, `doctor` and `upgrade` print
the exact command (`RATIFACT_CONFIG=<path> ratifact upgrade`). The `MEMORIA_PROYECTOS_*` variables keep working with
a deprecation notice until 1.1. Details: [docs/upgrade-v1.md](docs/upgrade-v1.md).

## Development

```
uv run --with pytest --with "mcp>=1.2,<2" pytest -q
```

The tests run against temporary folders and a temporary HOME: they never touch your configuration, clients or
projects. Publishing steps: [docs/publish.md](docs/publish.md).

Source: <https://github.com/EmaSleal/ratifact>.

## License

MIT — see [LICENSE](LICENSE).
