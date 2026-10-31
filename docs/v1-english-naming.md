# v1 in English — product name and naming glossary

Status: draft for review · Applies: structure in English, stored content in English, PyPI + GitHub
This document is the specification for the schema v1 → v2 migration and for renaming the server.

## 1. Product name

Requirements: free on PyPI (it becomes `uvx <name>`), no collision with an existing MCP server, says what is different (a project memory where only the user ratifies decisions, shared by every agent).

| Candidate | Meaning | PyPI | Known collisions |
|---|---|---|---|
| **ratifact** | *ratify* + *artifact*: decisions become records only when the user ratifies them | free | none found |
| **minutebook** | a company's minute book: the official record of resolutions | free | MinuteBox (legal SaaS, different market) |
| **charterkeep** | keeps the project charter: decisions, open items, tasks | free | none found |

Rejected (taken or colliding with existing MCP servers): accord-mcp, canon-mcp, project-lore, logbook-mcp, steward, project-memory, memoria-mcp, keystone-mcp, ledger names.
Recommendation: **ratifact** — short, coined (searchable), and it names the core governance rule.

Derived names (with `<name>` = chosen product name): PyPI package and CLI `<name>`; MCP server id `<name>`; env vars `<NAME>_CONFIG`, `<NAME>_LOG`, `<NAME>_BASE`; config dir `~/.config/<name>/` (projects.json); default memory root `<base>/.<name>/<project>` (today `<base>/.memorias/<project>`).

## 2. What does NOT change

- **IDs**: `ADR-NNN`, `P-NNN`, `T-NNN` keep their prefixes and numbers. Existing content references them (e.g. "depends on P-001"); renaming IDs would break those references.
- **Body text** of existing records (history untouched). Only frontmatter keys, state values and section headings are migrated (deterministic mapping, no model involved).
- `.project/` virtual prefix, `INDEX.md`, `docs/`, git-per-memory, commit-per-write.
- `user_quote` content: always verbatim, in the user's language.

## 3. Tools (26)

| Spanish | English | Note |
|---|---|---|
| listar_proyectos | list_projects | |
| obtener_contexto | get_context | |
| registrar_proyecto | register_project | |
| inicializar_memoria | init_memory | |
| instrucciones_proyecto | project_instructions | |
| configurar_pruebas | set_test_command | |
| registrar_decision | propose_decision | name states that every decision is born *proposed* |
| confirmar_decision | accept_decision | |
| confirmar_decisiones_lote | accept_decisions | batch, all-or-nothing |
| revisar_propuestas | review_proposals | |
| decidir_propuestas | decide_proposals | elicitation form |
| descartar_decision | reject_decision | |
| reemplazar_decision | supersede_decision | standard ADR term |
| registrar_pendiente | add_pending | keeps the `P-` prefix meaningful |
| cerrar_pendiente | close_pending | |
| buscar | search | |
| listar_documentos | list_documents | |
| leer_documento | read_document | |
| crear_documento | create_document | |
| guardar_documento | update_document | only existing files; modes `replace` / `append` |
| actualizar_indice | update_index | |
| registrar_sesion | log_session | |
| registrar_tarea | create_task | |
| actualizar_tarea | update_task | |
| devolver_tarea | request_changes | clearer than "return" |
| listar_tareas | list_tasks | |

Prompts: `inicio` → `start`, `cierre` → `close`.
Command: the old Spanish command (retired in 1.0.0) → **`/run-task`** (`$run-task` in Codex). Not `/task`: Claude Code already ships `/tasks` and the two would be confused.

## 4. Parameters

proyecto → project · titulo → title · decision → decision · justificacion → rationale · alternativas → alternatives · resumen → summary · id → id · cita_usuario → user_quote · ids → ids · desde_id → from_id · cantidad → limit · motivo → reason · id_anterior → old_id · id_nuevo → new_id · tema → topic · contexto → context · dueno → owner · resolucion → resolution · id_decision → decision_id · texto → query · max_resultados → max_results · carpeta → folder · ruta → path · desde_linea → from_line · hasta_linea → to_line · contenido → content · modo → mode · objetivo → goal · criterios_aceptacion → acceptance_criteria · decisiones → decisions · archivos → files · fuera_de_alcance → out_of_scope · notas → notes · repositorio → repo · estado → status · resultado → result · commit → commit · observaciones → findings · criterios_adicionales → additional_criteria · incluir_cerradas → include_closed · comando → command · nombre → name · memoria → memory · pruebas → tests

## 5. States

| Record | Spanish | English |
|---|---|---|
| Decision | propuesta / acordada / descartada / reemplazada | proposed / accepted / rejected / superseded |
| Pending item | abierta / cerrada | open / closed |
| Task | pendiente / en_curso / en_revision / devuelta / fallida / integrada / descartada | todo / in_progress / in_review / changes_requested / failed / merged / discarded |

## 6. Memory layout and record fields

Folders: decisiones/ → decisions/ · pendientes/ → pending/ · sesiones/ → sessions/ · tareas/ → tasks/
Views: acuerdos.md → DECISIONS.md · abiertas.md → OPEN.md · INDEX.md unchanged · esquema.json → schema.json

Frontmatter: titulo → title · estado → status · fecha → date · actualizada → updated · resumen → summary · reemplazada_por → superseded_by · tema → topic · dueno → owner · rama → branch · repositorio → repo · revisiones → reviews · commit, id unchanged

Section headings (migrated in existing records too; body untouched):
- Decision: Decisión → Decision · Justificación → Rationale · Alternativas consideradas → Alternatives considered · Confirmación → Acceptance · Descartada → Rejected · Resolución → Resolution
- Task: Objetivo → Goal · Criterios de aceptación → Acceptance criteria · Decisiones aplicables → Applicable decisions · Archivos involucrados → Files involved · Fuera de alcance → Out of scope · Notas → Notes · Cómo verificar → How to verify · Resultado → Result · Revisión N → Review N · Observaciones → Findings · Criterios adicionales → Additional criteria

## 7. Configuration (projects.json)

ruta → path · memoria → memory · escritura → writable · pruebas → tests · new: content_language (default `en`)
The migration rewrites projects.json keys in place (with a backup) and moves it to `~/.config/<name>/` only if the user agrees.

## 8. Migration v1 → v2 (per memory, automatic, one commit)

1. Rename folders and view files; rename `esquema.json` → `schema.json` with version 2.
2. Rewrite frontmatter keys and state values; rewrite known section headings; never touch body text or `user_quote`.
3. Regenerate DECISIONS.md / OPEN.md. INDEX.md stays as is until the next `close` regenerates it in English.
4. Commit `memory: migrate schema v1 → v2`; reversible with git.
Outside the memory (user action, assisted by `project_instructions`): paste new Claude project instructions, replace the CLAUDE.md/AGENTS.md block, update approval settings (`accept_decision`, `accept_decisions`, `register_project`, `create_*`, `propose_decision`, `add_pending`), relink `/run-task`.

## 9. Timing

Implement after the 14-day telemetry criterion (at least 300 calls, error rate below 1%) closes (~2026-10-17) so the stability window is not invalidated by the rename. Until then this document is the spec; review it and settle section 1 and the open choices below.

## Open choices
- Product name (section 1).
- `/run-task` vs another command name.
- Default memory root `.<name>/` vs keeping `.memorias/` for existing users.

## Resolved (2026-10-06)
- Product name: **ratifact** → package/CLI `ratifact`, env vars `RATIFACT_CONFIG` / `RATIFACT_LOG` / `RATIFACT_BASE`, config dir `~/.config/ratifact/`.
- Command: **`/run-task`** (`$run-task` in Codex).
- Default memory root: **`<base>/.ratifact/<project>`**; the v1 → v2 migration moves existing memories from `.memorias/` and updates projects.json.
Status of this document: approved spec; implementation after the 14-day telemetry criterion (~2026-10-17).

## Addendum (2026-10-17) — new tool in v1
- `amend_task(project, id, additional_criteria="", notes="")`: appends acceptance criteria and/or notes to a task in `todo` or `changes_requested`; rejects any other status. Written as an "Amendment N" block (date) in the task, one commit per amendment; original criteria untouched. No Spanish predecessor: it is born in English with the rename. Tool count in v1: 27.
- Task section headings add: Amendment N → (new), with sub-labels "Additional criteria" and "Notes".

## Addendum (2026-10-18) — names added later and execution plan

### New names to translate
- Parameters: resuelve → resolves · integraciones → integrations · redetectar → redetect · repositorio → repo (already listed).
- Parameter values: "(parcial)" marker in `resolves` → "(partial)"; the parser accepts both. Integration switch values `auto` / `off` unchanged.
- Frontmatter: creado → created · resuelve → resolves (same value format).
- Task section headings: Resuelve → Resolves · Cómo verificar → How to verify (already listed).
- Integration module and descriptor fields (ratifact/integraciones/ → ratifact/integrations/): nombre → name · alcance → scope (proyecto → project, usuario → user) · detectar → detect · prefijo → prefix · rol → role · limite → boundary · guia → guidance (planificar → plan, ejecutar → execute, verificar → verify, cerrar → close).
- Startup output: "# Pendientes abiertos (N)" → "# Open items (N)"; "Detalle: leer_documento(...)" → "Detail: read_document(...)"; "Integraciones:" → "Integrations:".
- Catalog record types: decision / pendiente / tarea → decision / pending / task.

### Execution plan
1. **Data migration (schema v2).** Inside each memory, automatic on first access under the lock: folders, frontmatter keys, state values, section headings, views (DECISIONS.md, OPEN.md), schema.json v2 with `content_language` ("es" for migrated memories, "en" for new ones). Safety: memory git status must be clean, tag `pre-v2` before, one commit `memory: migrate schema v1 → v2`. Tool names/parameters stay Spanish; state parameters accept Spanish and English; outputs use English states.
2. **Contract rename.** Tools, parameters, descriptions and responses in English (27 tools with amend_task), `/run-task`, RATIFACT_* env vars with MEMORIA_PROYECTOS_* fallback + deprecation notice until 1.1, follow-ups.
3. **Packaging.** PyPI via uvx and installer.

### Proposed (pending the user's confirmation)
- The `.memorias/` → `.ratifact/` root move and the projects.json key rename (§7) leave the automatic migration and become an explicit installer/upgrade step run with all clients closed (projects.json backup; custom memory paths never move). From step 1 on, the code reads both Spanish and English projects.json keys.
- `content_language` lives in each memory's schema.json instead of projects.json (§7).

## Addendum (2026-10-20) — read_task in v1

- `read_task(project, id)`: working brief of a task — frontmatter, full spec (Goal, Acceptance criteria, Resolves, Applicable decisions, Files involved, Out of scope, Notes, How to verify), every Amendment block, the status-relevant block in full (changes_requested → latest Review; in_review or failed → latest Result block) and a one-line index (heading · line range · size) of every other Result/Review block, readable with `read_document` and a range.
- `/run-task` step 1 calls `read_task`; planner-side reviews use it too.
- Born in English with the contract rename (no Spanish predecessor). Tool count in v1: 28 (26 renamed + amend_task + read_task).
