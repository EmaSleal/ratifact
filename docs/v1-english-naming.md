# v1 in English — product name and naming glossary

Status: draft for review · Applies: ADR-014 (structure in English), ADR-016 (stored content in English), ADR-015 (PyPI + GitHub)
This document is the specification for the schema v1 → v2 migration and for renaming the server.

## 1. Product name

Requirements: free on PyPI (it becomes `uvx <name>`), no collision with an existing MCP server, says what is different (a project memory where only the user ratifies decisions, shared by every agent).

| Candidate | Meaning | PyPI | Known collisions |
|---|---|---|---|
| **ratifact** | *ratify* + *artifact*: decisions become records only when the user ratifies them | free | none found |
| **minutebook** | a company's minute book: the official record of resolutions | free | MinuteBox (legal SaaS, different market) |
| **charterkeep** | keeps the project charter: decisions, open items, tasks | free | none found |

Rejected (taken or colliding with existing MCP servers): accord-mcp, canon-mcp, project-lore, logbook-mcp, steward, project-memory, memoria-mcp, keystone-mcp, ledger names.
Recommendation: **ratifact** — short, coined (searchable), and it names the core governance rule (ADR-011).

Derived names (with `<name>` = chosen product name): PyPI package and CLI `<name>`; MCP server id `<name>`; env vars `<NAME>_CONFIG`, `<NAME>_LOG`, `<NAME>_BASE`; config dir `~/.config/<name>/` (projects.json); default memory root `<base>/.<name>/<project>` (today `<base>/.memorias/<project>`).

## 2. What does NOT change

- **IDs**: `ADR-NNN`, `P-NNN`, `T-NNN` keep their prefixes and numbers. Existing content references them (e.g. "depends on P-003"); renaming IDs would break those references.
- **Body text** of existing records (ADR-016: history untouched). Only frontmatter keys, state values and section headings are migrated (deterministic mapping, no model involved).
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
| registrar_decision | propose_decision | name states that every decision is born *proposed* (ADR-011) |
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
Command: `/tarea` → **`/run-task`** (`$run-task` in Codex). Not `/task`: Claude Code already ships `/tasks` and the two would be confused.

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

ruta → path · memoria → memory · escritura → writable · pruebas → tests · new: content_language (default `en`, ADR-016)
The migration rewrites projects.json keys in place (with a backup) and moves it to `~/.config/<name>/` only if the user agrees.

## 8. Migration v1 → v2 (per memory, automatic, one commit)

1. Rename folders and view files; rename `esquema.json` → `schema.json` with version 2.
2. Rewrite frontmatter keys and state values; rewrite known section headings; never touch body text or `user_quote`.
3. Regenerate DECISIONS.md / OPEN.md. INDEX.md stays as is until the next `close` regenerates it in English.
4. Commit `memory: migrate schema v1 → v2`; reversible with git.
Outside the memory (user action, assisted by `project_instructions`): paste new Claude project instructions, replace the CLAUDE.md/AGENTS.md block, update approval settings (`accept_decision`, `accept_decisions`, `register_project`, `create_*`, `propose_decision`, `add_pending`), relink `/run-task`.

## 9. Timing

Implement after ADR-009 criterion 2 closes (~2026-10-17) so the stability window is not invalidated by the rename. Until then this document is the spec; review it and settle section 1 and the open choices below.

## Open choices
- Product name (section 1).
- `/run-task` vs another command name.
- Default memory root `.<name>/` vs keeping `.memorias/` for existing users.

## Resolved (2026-10-06, ADR-017)
- Product name: **ratifact** → package/CLI `ratifact`, env vars `RATIFACT_CONFIG` / `RATIFACT_LOG` / `RATIFACT_BASE`, config dir `~/.config/ratifact/`.
- Command: **`/run-task`** (`$run-task` in Codex).
- Default memory root: **`<base>/.ratifact/<project>`**; the v1 → v2 migration moves existing memories from `.memorias/` and updates projects.json.
Status of this document: approved spec; implementation after ADR-009 criterion 2 (~2026-10-17).
