# Optional integrations — design (ADR-024)

Status: draft for review · 2026-10-17 · becomes the task after T-007, before the v1 rename (ADR-014).

## Goal
ratifact adapts to the agent tooling the user already has (codegraph, engram, gentle-ai…) to get more out of it, without depending on it. With no integration installed, ratifact works exactly as today.

## Principles
1. **No proxy.** An MCP server cannot call another MCP; only the agent sees every tool. ratifact never spawns, wraps or calls other MCPs. Integration happens in the guidance the agent receives.
2. **Conditional guidance.** A signal on disk (e.g. `.codegraph/`) does not mean the current client has that MCP connected (Claude Desktop has no codegraph). Guidance is always phrased "if you have `codegraph_*` tools, …; otherwise …". The agent decides.
3. **Clear boundaries.** ratifact is the source of truth for agreed decisions, open items and task specs. Integrations never store decisions.
4. **User decides.** Default `auto` (active when detected). Per-project switch to turn one off.
5. **Adding an integration = adding one file.** No tool-contract change.

## Integration descriptor
One module per integration in `ratifact/integraciones/` (English names after the v1 rename):

| Field | Example (codegraph) |
|---|---|
| `name` | `codegraph` |
| `detect(project_root)` | `.codegraph/` exists |
| `tool_prefix` | `codegraph_` |
| `role` | Code structure: symbols, callers, dependencies |
| `boundary` | Never decisions or task status |
| `guidance` | dict phase → text: `planning`, `task_explore`, `task_verify`, `task_close` |

Initial set:
- **codegraph** — detect `.codegraph/`. `task_explore`: after reading the spec and before opening files, call `codegraph_context` with the objective + listed files. `task_verify`: check callers of changed symbols to confirm the blast radius. `planning`: if available, use it to fill `archivos` precisely.
- **engram** — detect engram install (signal to define: binary on PATH or its data dir). Migrates today's ad-hoc text in `app.py`, `plantillas.py` and `skills/tarea/SKILL.md`: engram for technical learnings; decisions only through ratifact; on conflict ratifact wins.
- **gentle-ai** — detect `.atl/`. Guidance: the orchestrator, sub-agents and skills may implement; the spec is the contract (today's SKILL.md line).

## Where guidance is injected
- `obtener_contexto`: one line "Integrations: codegraph (detected), engram (detected)" + `planning` fragments.
- `registrar_tarea` response and the task file: detected integrations at registration time.
- `/tarea` skill: a step that tells the agent to read the integration fragments for the task phases (served by ratifact, so the skill file stays generic).
- Task `resultado`: one line "Integrations used: codegraph (n queries)" — self-reported, the only available signal since ratifact's telemetry cannot see other MCPs.

## Configuration
`projects.json` per project: `"integraciones": {"codegraph": "auto" | "off"}` (absent = auto). Set through `actualizar_proyecto(..., integraciones=...)` — this is a **new parameter**, so it must ship before the English contract freeze.

## Measurement
- Before/after with `analizar_uso.py` (code reads through leer_documento by project, added in T-007).
- Self-reported integration usage in task results.

## Open questions
1. Engram detection signal: binary on PATH, data dir, or only conditional guidance with no detection?
2. Should `planning` guidance appear in `obtener_contexto` every chat (startup cost, today ~1,389 tokens, target < 2,000) or only in `registrar_tarea`?
3. Installer (PyPI task): detect gentle-ai/codegraph and ask the user which integrations to enable, or just report them?
