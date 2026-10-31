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

From a clone instead of PyPI: `uv tool install <path to the clone>`. After each update follow the procedure in
[Version drift](#version-drift): merge → `uv tool install --reinstall <path>` → restart the clients → `ratifact doctor`.

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
`run-task` skill is linked into Claude Code, Pi and Codex by `ratifact install --apply`. A link that exists as a real file or folder is never replaced: the
plan says to remove it by hand. The links point inside the installed package; if a reinstall moves it (for example
`uv tool install --reinstall` with another Python version), `ratifact doctor` reports the links as pending and
`ratifact install --apply` fixes them.

## Commands

| Command | What it does |
|---|---|
| `ratifact serve` | The MCP server over stdio (what the clients launch). |
| `ratifact install [--apply] [--client NAME]` | Configures the MCP clients and links /run-task (plan unless `--apply`). |
| `ratifact doctor` | Read-only diagnosis: version and where it runs from, configuration, each project's code, memory, schema and git status, integrations, the state of each client (configured with ratifact / old configuration / not configured / not found), the build id, whether a local source is newer than the installation, the running `ratifact serve` processes that started before it (see [Version drift](#version-drift)) and the pending actions. Exit code 1 if something is pending. |
| `ratifact upgrade [--apply]` | One-time upgrade from memoria-proyectos (below). |
| `ratifact report [--days N] [--project P] [--log PATH]` | Usage summary from the local telemetry log (`~/.local/state/ratifact/uso.jsonl`: tool, size, duration and error of each call — never content). |
| `ratifact --version` | Installed version. |

## Integrations

Optional integrations add conditional guidance to `get_context`, `create_task` and `update_task`; ratifact never
calls another MCP server.

| Integration | Detected by | Role |
|---|---|---|
| codegraph | a `.codegraph/` folder in the project | code structure for planning and checking a task's scope |
| gentle-ai | a `.atl/` folder in the project | the task runs as its delegated-direct route (never SDD), is its ODD feature document, and RDD (if on) reviews it before `in_review`; whether to delegate follows ratifact's delegation policy |
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

## Delegation

Delegation policy (ADR-036): ratifact, not the executing agent, decides whether a task is delegated.
`"delegation": "required" | "suggested" | "off"` goes in `settings.json` next to `"models"` (global; default
`required`); a project exception is set with `update_project("my-app", delegation="off")` (`inherit` removes it), and a
task exception with `create_task(..., delegation="off")` or `amend_task(..., delegation="required")` while planning
(stored as `delegation:` in the task's frontmatter). Precedence: task > project > global > `required`. Use `off` for a
task that touches security, is cross-cutting, or depends on diagnosing a cause the spec does not know yet.

- `required`: `update_task(..., "in_progress")` returns an imperative "Delegation" block — the main session
  orchestrates and does not write the code; exploration in an explore worker, implementation in write workers,
  verification in a verify worker that did not see the implementation, each with its role's model (or the session's);
  briefs carry the full spec; the orchestrator reviews the complete diff before `in_review`; after two failed
  verifications the orchestrator takes over and declares `escalated: write`.
- `suggested`: the block is a suggestion. `off`: no delegation block.
- The result carries its own line, separate from `Integrations used:` (which lists integrations only, never role
  names): `Workers: explore/haiku×1, write/sonnet×2, verify/sonnet×1` (plus `escalated: write`), or
  `Workers: none — reason: <why>`. With `required`, `update_task(..., "in_review")` without a valid `Workers:` line
  still changes the status but answers with a warning.
- Extended format (ADR-041, corrects ADR-036 §4–§5): `Workers: <role>/<model>×<n>, …[, rework: <role>×<n>, …][, escalated: <role>][ — note: <free text>]`.
  `<role>/<model>×<n>` counts initial briefs only; `rework: <role>×<n>` counts re-sends of that role after a
  verification found a defect (the role must appear among the workers, n ≥ 1); everything after ` — ` is a note the
  parser ignores. No parentheses: rework goes in `rework:`, comments in `— note:`. Example:
  `Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1, rework: write×1 — note: resumed once for the verify fix`.
  ADR-036 lines stay valid.
- Fixing a line without duplicating: if the warning says the line is invalid it proposes a corrected one when it can
  derive it; sending only that line with `update_task(..., "in_review")` replaces the `Workers:` line of the latest
  result block (or appends it there) instead of creating a new block.
- Audit: `in_progress` records `routing: explore=<m>,write=<m>,verify=<m> · delegation=<policy> · build=<build> ·
  at=<ISO 8601 time, to the minute>` in the task's frontmatter (`session` for a role without a model; overwritten on
  re-runs; `build=` and `at=` since T-016, ADR-037 — older tasks keep the shorter form and are still read). `ratifact
  report` takes the period from `at=` when present (`updated` otherwise). `ratifact report` measures compliance
  per project (required tasks with real workers, escalations) and compares delegated and non-delegated tasks in
  reviews and in_progress → in_review duration; tasks without `routing:` are counted apart.
  Since ADR-041 routing ends with `· client=<name>/<version>`, taken from the MCP `clientInfo` of the initialize
  handshake (sanitized: no spaces, no `·`, no newlines, max 64 chars; `client=unknown` if unavailable), and every new
  `uso.jsonl` row has a `client` field. Values are recorded as received, without normalization (P-025). `ratifact
  report` also measures, among delegated tasks (last valid `Workers:` line of each), how many had rework, the total
  re-sends per role, escalations and the rework rate (with rework / delegated), plus a per-client breakdown (`client=`
  from routing, `unknown` if missing) with tasks, delegation compliance and rework rate. `ratifact doctor` shows
  each project's effective policy (e.g. `delegation=required (global)`).

## Version drift

There are three copies of ratifact: the source (a clone), the installation (the uv tool directory, which the
/run-task skills link to) and the running server (one `ratifact serve` per client, which keeps the code it started
with). They drift apart when you merge without reinstalling, or reinstall without restarting a client (ADR-037).
The procedure after every change is:

```bash
# 1. merge into main   2. reinstall
uv tool install --reinstall <path to the clone>
# 3. restart every client (Claude Desktop, Claude Code, Codex, Pi)   4. check
ratifact doctor
```

What reveals a drift:

- **Build id.** Each server computes `<version>+<7 hex>` at startup (content hash of its package, skills included,
  bytecode excluded). `get_context` shows `ratifact <build>` on its first line and `routing:` records it per task.
- **Stale server.** The server re-checks its own package files (stat only, cached 5 s). If they changed or vanished
  since it started, `get_context` shows a ⚠ line below the build asking to restart that client, every other tool
  prepends the same warning, and `update_task(..., "in_progress")` is refused without changing anything: restart the
  client and repeat it (a task never starts with guidance that may be out of date).
- **Source newer than the installation.** When uv installed ratifact from a local folder (its tool receipt), `doctor`
  and `get_context` compare that folder's package with the installed one and ask to reinstall, with the command.
  Installations from PyPI do not show it.
- **`ratifact doctor`** also lists the running `ratifact serve` processes (PID, start time, parent process). A reinstall
  rewrites every file even when nothing changed, so a process that started before the installation is flagged only
  when its content differs: each server records its startup build in `~/.local/state/ratifact/servers/<pid>.json`
  (ADR-038; removed on exit, dead PIDs pruned at startup). Same content → "nothing to do"; no record (a server older
  than this) → "the content may be identical", and `get_context` in that client gives the definitive answer. doctor
  only reads: it never writes, signals or stops anything (Linux and macOS; elsewhere it says the list is unavailable).
- The server's own check works the same way: a changed fingerprint is confirmed by the content hash once, so a
  reinstall with identical code does not trigger the warning or the `in_progress` refusal.

`ratifact install --apply` and `ratifact upgrade --apply` end by reminding you to restart the clients and run
`ratifact doctor`. A server older than T-016 cannot diagnose itself; `doctor` still shows it.

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
