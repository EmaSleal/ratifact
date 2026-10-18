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
- **gentle-ai** (project) — `ejecutar`: the orchestrator, sub-agents and skills may implement; the spec is the contract (moves today's SKILL.md line).
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

## Installer (PyPI task)
Reports detected integrations and how to disable one. Never asks interactively.

## Measurement
- `analizar_uso.py`: code reads through leer_documento by project (T-007).
- Task results: one line "Integraciones usadas: codegraph (n consultas)" — self-reported; ratifact cannot see other MCPs.
