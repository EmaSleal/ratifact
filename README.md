# ratifact

A local [MCP](https://modelcontextprotocol.io) server that turns each repository into the persistent memory of its
project. Decisions (ADRs), open items, code tasks and session logs live as Markdown files in a git repository of their
own, outside the code repository, so no branch or checkout ever changes them. Any MCP client (Claude Desktop, Claude
Code, Pi, Codex) reads and writes the same memory through 28 tools. A full `/run-task` run (`$run-task` in Codex) is
validated with Codex CLI; see [Known limitations on Codex](#known-limitations-on-codex).

- **Decisions are ratified, not assumed.** Every decision is recorded as `proposed`; it only becomes `accepted` through
  `accept_decision`, with the user's literal words, and the client asks the user to approve that call.
- **Tasks travel from the chat to the coding agent.** A change agreed in a chat is recorded with `create_task`; the
  coding agent runs it with `/run-task T-NNN` (`$run-task T-NNN` in Codex), on its own branch, and leaves the result
  for review.
- **Everything is plain files under git.** Views such as `DECISIONS.md` and `OPEN.md` are regenerated from the
  records; nothing is deleted, only changes status.

Linux and macOS (Windows through WSL). Python 3.10 or newer. Spanish documentation: [LEEME.md](https://github.com/EmaSleal/ratifact/blob/main/LEEME.md).

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
`RATIFACT_BASE` says otherwise; `RATIFACT_CONFIG` and `RATIFACT_LOG` override the configuration and the usage log, and
`RATIFACT_CLAUDE_CODE_TEMP` overrides the Claude Code temporary folder that `ratifact doctor` reviews.

## /run-task

`ratifact install --apply` links the `run-task` skill from the installed package:

- Claude Code: `~/.claude/skills/run-task` (the older `~/.claude/commands/run-task.md` link is removed if it is ours)
- Pi: `~/.pi/agent/prompts/run-task.md` (and `~/.pi/agent/skills/run-task` if that folder exists)
- Codex: `~/.codex/skills/run-task` and `~/.agents/skills/run-task` (the whole folder: Codex does not follow a linked
  `SKILL.md`)

In the repository, `/run-task T-001` (Codex: `$run-task T-001`) reads the task with `read_task`, creates its branch
from main, implements it, runs the project's tests and leaves the task `in_review` (or `failed`) with the result. The
`run-task` skill is linked into Claude Code, Pi and Codex by `ratifact install --apply`. A link that exists as a real file or folder is never replaced: the
plan says to remove it by hand. The links point inside the installed package; if a reinstall moves it (for example
`uv tool install --reinstall` with another Python version), `ratifact doctor` reports the links as pending and
`ratifact install --apply` fixes them.

Create verification copies with `git archive` from the task branch (versioned files only), never by copying the working
tree, and never copy production data or database dumps into temporary space. Before reporting `in_review` or `failed`,
delete only this session's task-created temporary copies and keep the result self-contained, with evidence in the result
or repository rather than temporary-file references.

## Codex

Codex (CLI, IDE extension and desktop app) is a supported client: `ratifact install --apply` configures
`~/.codex/config.toml`, and `/run-task` runs there as `$run-task T-001`. A full `/run-task` run was
validated with Codex CLI, not in the IDE extension or the desktop app, which share the same configuration. It has
two known limitations.

### Known limitations on Codex

**Sandbox.** Codex runs commands in a sandbox that restricts the network and writes outside the project. A
verification command that downloads dependencies (for example `uv run --with ...`) may fail to start. The typical
symptom is a name-resolution (DNS) error toward the package index, or a read-only package cache.

The permission profile Codex runs with needs network access and write access to the package manager's cache. Example
for `~/.codex/config.toml` (checked with Codex CLI 0.169; key names may change between versions), where the filesystem
entry is the absolute path of your package manager's cache (write it absolute, not with `~`), here uv's:

```toml
[permissions.<profile>.network]
enabled = true

[permissions.<profile>.filesystem]
"/home/<user>/.cache/uv" = "write"
```

`codex sandbox <command>` runs a command inside the sandbox, and `-c` lets you try a permission change before applying
it. Enabling the network opens it completely in that configuration: a domain allow-list did not restrict it in the
check. Disabling the sandbox is not recommended as a general setup.

A project whose tests use Docker or Testcontainers also needs access to the Docker socket. Allowing it amounts to full
control over the Docker daemon. That combination with the sandbox on has not been checked by this project.

**Models per role.** The models in `settings.json` are a single value for all clients, and a client that does not
offer them runs the roles on the session's model. See [Model routing](#model-routing).

## Commands

| Command | What it does |
|---|---|
| `ratifact serve` | The MCP server over stdio (what the clients launch). |
| `ratifact install [--apply] [--client NAME]` | Configures the MCP clients and links /run-task (plan unless `--apply`). |
| `ratifact doctor` | Read-only diagnosis: version and where it runs from, configuration, each project's code, memory, schema and git status, integrations, the state of each client (configured with ratifact / old configuration / not configured / not found), the build id, whether a local source is newer than the installation, the running `ratifact serve` processes that started before it (see [Version drift](#version-drift)), Claude Code temporary-space usage (`/tmp/claude-<uid>/`, checked on Linux and overridden by `RATIFACT_CLAUDE_CODE_TEMP`; file names that look like data dumps or env files raise a warning, certificate and key names are only listed, names are a hint and never a guarantee, and a walk cut short shows sizes as "at least" and counts as a warning), and pending actions. Exit code 1 if something is pending. |
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

The models in `settings.json` are a single value for all clients. In a client that does not offer those models (for
example Codex, when they are another client's aliases), the roles run on the session's model. A task records two
different things: its `routing` field stores what was requested, and the Workers line stores what was actually used.
When all roles run on the same model there is no verification on a different model, so the backup verification on
another model is not met; on Codex that was the observed case. ratifact does not warn about this at run time.

When at least one role is set, `update_task(..., "in_progress")` adds a "Model routing" block (each role, its model
and whether it comes from `global` or `project`): it is your explicit request to set that model when the agent
delegates the role; a client that cannot choose a sub-agent's model ignores it, and roles without a model use the
session's model. With no configuration the response is unchanged. An invalid `settings.json` never breaks a tool
(it is ignored with a warning in that block); `ratifact doctor` reports it without changing it and shows each
project's effective models (or `models: session default`).

## Token usage in `report`

`ratifact report` can show the real token usage of each task run with Claude Code, split between the main session and
the workers and by model (to judge whether delegating saves the main model's budget). It is off by default: turn it on
with `"token_usage": "on"` in `settings.json`, next to `"models"` and `"delegation"` (`"off"` or absent keeps it off; an
invalid value is treated as off and `ratifact doctor` reports it). With it off, `report` opens no transcript file.

```json
{"token_usage": "on"}
```

- Source: the local Claude Code transcripts, `$CLAUDE_CONFIG_DIR/projects` or else `~/.claude/projects`. It reads only
  metadata fields of each line (timestamp, working folder, branch, model, ids and the four token counters of `usage`),
  never the content of any message. Nothing is stored: it is computed on each run.
- A task's usage counts the project's sessions (any line whose working folder is the project's folder or inside it,
  also in multi-repo projects) that were active at the moment the task went to `in_progress` or to `in_review` (a
  line within two minutes of that moment). Of those sessions, the messages between the task's `in_progress` and its
  next `in_review` (one window per run) count, on whichever branch. If several sessions were active at the same
  moment, only those with a line on the task's branch inside the window count; if none has it, the task shows as
  `ambiguous`. A message is counted once, and never for two tasks.
- Per task with `routing:` in the period: its delegation policy and, for the main session and for the workers (with
  their number), `in`, `out`, `cache write` and `cache read` per model. Per project, the average per task of output and
  cache-read tokens for delegated and not delegated tasks, over the tasks with data, with the median per task on a
  second line. A task whose windows add up to more than 8 hours carries a `long window` warning (it may include other
  work of the same session); it is shown and counted. Only tasks whose result has a
  valid `Workers` line enter the averages; a task without one (for example, still in progress) is listed with its
  figures but counts in neither group. A task with no data (another
  client, or transcripts already deleted) shows `no data`; an `ambiguous` task is left out of the summaries.
- It only covers Claude Code; transcripts are deleted by Claude Code after its retention period, so old tasks lose
  their data. The breakdown is per model, not per role.

## Delegation

Delegation policy: ratifact, not the executing agent, decides whether a task is delegated.
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
- Extended format: `Workers: <role>/<model>×<n>, …[, rework: <role>×<n>, …][, escalated: <role>][, skipped: explore][ — note: <free text>]`.
  `<role>/<model>×<n>` counts initial briefs only, even with several workers of the same role in parallel (two parallel
  writers are `Workers: write/sonnet×2`); `rework: <role>×<n>` counts re-sends of that role caused by a defect found by
  the verifier or by the orchestrator's diff review (the role must appear among the workers, n ≥ 1). A note starts at
  ` — note:` (canonical) or at ` - note:` / ` -- note:`, and `none - reason:` / `none -- reason:` are accepted
  (`Workers: write/sonnet×1 - note: x`); an ASCII hyphen anywhere else (`Workers: write/sonnet×1 - resumed once`)
  separates nothing and is an invalid token. The parser ignores the note's text. No parentheses: rework goes in `rework:`, comments in `— note:`. Example:
  `Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1, rework: write×1 — note: diff review found a missing test`.
  Lines in the earlier format (without `rework:` or a note) stay valid.
  Exploration may be skipped only when the main session already explored the task's files in this session: declare it
  with `skipped: explore` in the head of the line and put the reason in the note, which is then required
  (`Workers: write/sonnet×1, verify/sonnet×1, skipped: explore — note: already explored while planning`; without the
  note, or together with an explore worker, the line is invalid; write and verify can never be skipped). If the verify
  model is not available (usage limit or API error), the verification is re-run in a new verify worker with another
  available model other than the writer's, listed in `Workers:` with its own role/model and the reason in the note; it
  is never skipped. With `required`, a valid line with neither an explore worker nor `skipped: explore` gets a soft
  warning on `in_review`.
- Fixing a line without duplicating: if the warning says the line is invalid it proposes a corrected one when it can
  derive it; sending only that line with `update_task(..., "in_review")` replaces the `Workers:` line of the latest
  result block (or appends it there) instead of creating a new block.
- Audit: `in_progress` records `routing: explore=<m>,write=<m>,verify=<m> · delegation=<policy> · build=<build> ·
  at=<ISO 8601 time, to the minute>` in the task's frontmatter (`session` for a role without a model; overwritten on
  re-runs; `build=` and `at=` are written on newer tasks — older tasks keep the shorter form and are still read). `ratifact
  report` takes the period from `at=` when present (`updated` otherwise). `ratifact report` measures compliance
  per project (required tasks with real workers, escalations) and compares delegated and non-delegated tasks in
  reviews and in_progress → in_review duration; tasks without `routing:` are counted apart.
  Routing also ends with `· client=<name>/<version>`, taken from the MCP `clientInfo` of the initialize
  handshake (sanitized: no spaces, no `·`, no newlines, max 64 chars; `client=unknown` if unavailable), and every new
  `uso.jsonl` row has a `client` field. Values are recorded as received, without normalization. `ratifact
  report` also measures, among delegated tasks (last valid `Workers:` line of each), how many had rework, the total
  re-sends per role, escalations and the rework rate (with rework / delegated), plus a per-client breakdown (`client=`
  from routing, `unknown` if missing) with tasks, delegation compliance and rework rate. `ratifact doctor` shows
  each project's effective policy (e.g. `delegation=required (global)`).

## Version drift

There are three copies of ratifact: the source (a clone), the installation (the uv tool directory, which the
/run-task skills link to) and the running server (one `ratifact serve` per client, which keeps the code it started
with). They drift apart when you merge without reinstalling, or reinstall without restarting a client.
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
  (removed on exit, dead PIDs pruned at startup). Same content → "nothing to do"; no record (a server older
  than this) → "the content may be identical", and `get_context` in that client gives the definitive answer. doctor
  only reads: it never writes, signals or stops anything (Linux and macOS; elsewhere it says the list is unavailable).
  Only a process with that record counts as a server: the wrapper through which Claude Desktop on Linux launches the
  MCP (its parent, also `ratifact serve` on the command line, without a record) is shown inside its server's entry
  ("wrapper <pid>, <client>"), and any other process without a record is listed apart as "Unregistered processes" and
  not counted. doctor also warns when it runs on native Windows (not supported: install ratifact inside WSL2,
  with the repositories on the WSL filesystem, not under `/mnt/c`), notes when it runs inside WSL, and warns about a
  registered repository under `/mnt/` (slow, with git differences).
- The server's own check works the same way: a changed fingerprint is confirmed by the content hash once, so a
  reinstall with identical code does not trigger the warning or the `in_progress` refusal.

`ratifact install --apply` and `ratifact upgrade --apply` end by reminding you to restart the clients and run
`ratifact doctor`. A server that predates the build/PID registry cannot diagnose itself; `doctor` still shows it.

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
a deprecation notice until 1.1. Details: [docs/upgrade-v1.md](https://github.com/EmaSleal/ratifact/blob/main/docs/upgrade-v1.md).

## Development

```
uv run --with pytest --with "mcp>=1.2,<2" pytest -q
```

The tests run against temporary folders and a temporary HOME: they never touch your configuration, clients or
projects. Publishing steps: [docs/publish.md](https://github.com/EmaSleal/ratifact/blob/main/docs/publish.md).

Source: <https://github.com/EmaSleal/ratifact>.

## License

MIT — see [LICENSE](https://github.com/EmaSleal/ratifact/blob/main/LICENSE).
