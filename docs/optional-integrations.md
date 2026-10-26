# Optional integrations — design (ADR-024, ADR-025)

Status: agreed · 2026-10-17 · implemented by T-008, before the v1 rename (ADR-014).

## Goal
ratifact adapts to the agent tooling the user already has (codegraph, engram, gentle-ai…) to get more out of it, without depending on it. With no integration installed, ratifact works exactly as today.

## Principles
1. **No proxy.** An MCP server cannot call another MCP; only the agent sees every tool. ratifact never spawns, wraps or calls other MCPs. Integration happens in the guidance the agent receives.
2. **Conditional guidance.** A signal on disk (e.g. `.codegraph/`) does not mean the current client has that MCP connected (Claude Desktop has no codegraph). Guidance is always phrased "if you have `codegraph_*` tools, …; otherwise …". The agent decides.
3. **Clear boundaries.** ratifact is the source of truth for agreed decisions, open items and task specs. Integrations never store decisions.
4. **User decides.** Default `auto`. Per-project switch to turn one off.
5. **Adding an integration = adding one file.** No tool-contract change.

## Scopes (ADR-025)
- **Project-scoped** — detected by a signal in the project folder (multi-repo: in any repo folder). codegraph: `.codegraph/`. gentle-ai: `.atl/`.
- **User-scoped** — not detected (no per-project signal; the client's MCPs are invisible to ratifact). Guidance-only, always conditional. engram.

## Integration descriptor
One module per integration in `ratifact/integraciones/` (English names after the v1 rename):

| Field | Example (codegraph) |
|---|---|
| `nombre` | `codegraph` |
| `alcance` | `proyecto` \| `usuario` |
| `detectar(raiz)` | `.codegraph/` exists (project scope only) |
| `prefijo` | `codegraph_` |
| `rol` / `limite` | Code structure: symbols, callers, dependencies / never decisions or task status |
| `guia` | dict phase → text: `planificar`, `ejecutar`, `verificar`, `cerrar` |

Initial set:
- **codegraph** (project) — `planificar`: if available, use it to fill `archivos` precisely. `ejecutar`: after reading the spec and before opening files, call `codegraph_context` with the objective + listed files. `verificar`: check callers of changed symbols to confirm the blast radius.
- **gentle-ai** (project) — revised by T-014 (ADR-033, ADR-034). `execute`: a ratifact task is gentle-ai's **delegated-direct** route — never SDD, no SDD artifacts; whether to delegate is set by ratifact's delegation policy (T-015, ADR-036), not by gentle-ai thresholds — the old "4+ files" / "2+ non-trivial files" criterion and "otherwise implement directly" were removed; the ratifact task is the **ODD** feature document, so no other ODD document is created. `verify`: verification in a clean worker; if **RDD** is on, the review of the finished change runs before `update_task(in_review)` and the result summarizes its receipt (depth, findings, corrections); if RDD is off, no review is started. ratifact neither enables nor blocks RDD. Prefix: `gentle-ai` (no longer `sdd-`).
- **engram** (user) — `cerrar`: technical learnings may go to engram; decisions only through ratifact; on conflict the agreed decision wins (moves today's text in app.py, plantillas.py, SKILL.md).

## Injection points (ADR-025)
| When | What the agent receives | Cost |
|---|---|---|
| `obtener_contexto` (planning) | One line "Integraciones: codegraph (detectada), gentle-ai (detectada) · engram (si está disponible)" + one `planificar` line per integration | ~50 tokens/integration; startup stays < 2,000 |
| `registrar_tarea` | Only the detected-integrations line | minimal |
| `actualizar_tarea(…, "en_curso")` (step 1.6 of `/tarea`) | Full `ejecutar` + `verificar` + `cerrar` guidance, computed at that moment | 0 extra calls |

Guidance is never written into the task file (stale on reruns). Disabled integrations (`off`) never appear.

## Configuration
`projects.json` per project: `"integraciones": {"codegraph": "off"}` (absent = auto). Set through `actualizar_proyecto(nombre, integraciones="codegraph=off,gentle-ai=auto")` — **new parameter**, must ship before the English contract freeze. Unknown integration names are rejected with the list of known ones.

## Model routing (T-014, ADR-033 §2, ADR-035)
Independent of any integration. The user sets a model per delegated role — `explore`, `write`, `verify`:
- **Global:** `settings.json` next to the active `projects.json` (`CONFIG.parent`), `{"models": {"explore": "haiku", "write": "sonnet", "verify": "sonnet"}}`. Created by hand; read on every call. `projects.json` gets no new top-level keys (every top-level key there is a project).
- **Per project:** `"models"` in the project's entry, set with `update_project(name, models="explore=haiku,write=sonnet")`; `inherit` removes a role's exception. Merged role by role: project wins, missing roles inherit the global value.
- **Delivery:** `update_task(..., "in_progress")` appends a "Model routing" block when at least one role is set (with or without integrations): each role, its model and its origin (global/project). It is the user's explicit request to set that model when delegating the role — which is what gentle-ai requires before setting `model` on a generic delegation. A client that cannot choose a sub-agent's model ignores it; roles without a model inherit the session's model. No configuration → the response is byte-for-byte unchanged.
- **Errors:** an invalid `settings.json` (bad JSON, unknown roles, empty values) is ignored with a warning in that block and never breaks a tool; `ratifact doctor` reports it without modifying it and shows each project's effective models.
- **Reporting:** superseded by ADR-036 — workers and models go in the result's own `Workers:` line (see Delegation below); `Integrations used:` lists integrations only. One line summarizes the RDD receipt if a review ran.
- The Model routing block is the same under every delegation policy.

## Delegation (T-015, ADR-036)
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
- Audit: `in_progress` records `routing: explore=<m>,write=<m>,verify=<m> · delegation=<policy> · build=<build> ·
  at=<ISO 8601 time, to the minute>` in the task's frontmatter (`session` for a role without a model; overwritten on
  re-runs; `build=` and `at=` since T-016, ADR-037 — older tasks keep the shorter form and are still read). `ratifact
  report` takes the period from `at=` when present (`updated` otherwise). `ratifact report` measures compliance
  per project (required tasks with real workers, escalations) and compares delegated and non-delegated tasks in
  reviews and in_progress → in_review duration; tasks without `routing:` are counted apart. `ratifact doctor` shows
  each project's effective policy (e.g. `delegation=required (global)`).

## Installer (PyPI task)
Reports detected integrations and how to disable one. Never asks interactively.

## Measurement
- `analizar_uso.py`: code reads through leer_documento by project (T-007).
- Task results: one line "Integraciones usadas: codegraph (n consultas)" — self-reported; ratifact cannot see other MCPs.
