# memoria-proyectos (ratifact) — instalación

Servidor MCP local: `servidor.py`. Proyectos registrados: `projects.json`.
Desde la v1 (T-011) el contrato está en inglés: herramientas, parámetros, descripciones y respuestas
(`docs/v1-english-naming.md`). Pasos para usuarios existentes después de actualizar: `docs/upgrade-v1.md`.

Variables de entorno: `RATIFACT_CONFIG` (projects.json), `RATIFACT_LOG` (telemetría) y `RATIFACT_BASE` (carpeta de
proyectos). Las anteriores `MEMORIA_PROYECTOS_*` siguen funcionando como respaldo hasta 1.1 (gana la nueva; el log del
servidor avisa una vez por variable). Sin variable, la configuración es `~/.config/ratifact/projects.json` si existe, si
no `~/.config/memoria-proyectos/projects.json` (no se mueve ni reescribe nada).

## 1. Claude Desktop
Agregue esto a `~/.config/Claude/claude_desktop_config.json` (dentro de `"mcpServers"`) y reinicie la app:

```json
"memoria-proyectos": {
  "command": "uv",
  "args": ["run", "--script", "/home/mano-pc/Projects/.memoria-proyectos/servidor.py"],
  "env": { "RATIFACT_CONFIG": "/home/mano-pc/Projects/.memoria-proyectos/projects.json" }
}
```
Sin `uv`: `pip install "mcp>=1.2,<2"` y use `"command": "python3", "args": ["/home/mano-pc/Projects/.memoria-proyectos/servidor.py"]`.
Si Claude Desktop no encuentra `uv`, use la ruta absoluta (`which uv`).

## Nota de versión
El servidor fija `mcp>=1.2,<2` en la cabecera de `servidor.py`. La serie 2.x de la librería `mcp` cambió la API y el servidor
se desconecta al arrancar. No quite ese límite sin probar antes con `./diagnostico.sh`.
Sin `uv`, instale igual: `pip install "mcp>=1.2,<2"`.

## 2. Claude Code
```bash
claude mcp add memoria-proyectos --scope user \
  -e RATIFACT_CONFIG=/home/mano-pc/Projects/.memoria-proyectos/projects.json \
  -- uv run --script /home/mano-pc/Projects/.memoria-proyectos/servidor.py
```

## 3. Instrucciones del proyecto en claude.ai
El texto exacto (en inglés, con los nombres de herramientas v1) lo devuelve `project_instructions("<proyecto>")`:
péguelo tal cual en *Project instructions*. Empieza así:

> project: game
> At the start of every chat, call `get_context("game")` before answering; assume nothing that is not there.
> When we reach a decision, record it with `propose_decision` (it stays proposed). Only if I accept it explicitly, call `accept_decision` with my literal words in `user_quote`; the app will ask me to approve it.
> …

## 4. Agregar otro proyecto
En cualquier chat con el MCP conectado, pida: "registra el proyecto <nombre> con el código en <ruta>".
`register_project` lo agrega a `projects.json`, crea su memoria (por defecto en `~/Projects/.memorias/<nombre>`,
con repo git propio) y devuelve las instrucciones exactas para pegar en el proyecto de Claude y en CLAUDE.md/AGENTS.md.
Para recuperar esas instrucciones de un proyecto existente: `project_instructions("<nombre>")`.
Recomendado: marcar `register_project` como "requiere aprobación" igual que `accept_decision`.

### Actualizar un proyecto ya registrado

`update_project(name, path="", tests="", repo="", redetect=False, integrations="")` corrige projects.json sin
editarlo a mano; reemplaza a la antigua `configurar_pruebas` (eliminada). Indique al menos uno de estos campos
(sin ninguno, la herramienta falla y no toca el archivo):
- `path`: nueva carpeta del código, cuando el proyecto se movió. Mismas validaciones que `register_project`
  (debe quedar dentro de la carpeta de proyectos, ser una carpeta existente, y no contener la memoria del
  proyecto — ADR-010; el mensaje de rechazo es distinto al del alta, porque aquí mover la memoria de un
  proyecto existente no está soportado). La respuesta indica la ruta vieja y la nueva. Si el proyecto es de
  varios repositorios y el comando de pruebas guardado queda con claves que ya no son repos bajo la ruta nueva, el
  cambio se aplica igual (no bloquea) pero la respuesta avisa cuáles quedaron huérfanas ("orphan tests") y sugiere
  `redetect=True`.
- `tests`: comando con que `/run-task` verifica el trabajo. En proyectos de varios repositorios, `repo`
  indica a cuál se aplica.
- `redetect=True`: vuelve a detectar el comando a partir de los archivos del proyecto, en vez de darlo con
  `tests` (ambos a la vez son incompatibles). En un proyecto de un solo repositorio redetecta el comando
  completo; en uno de varios repositorios redetecta todos, o solo `repo` si se indica. Es la forma de
  recuperar el comportamiento que antes tenía `configurar_pruebas()` llamada sin argumentos.
- `integrations`: activa o apaga integraciones opcionales, p. ej. `"codegraph=off,gentle-ai=auto"` (valores
  `auto`|`off`; por defecto `auto`). Se guarda en `projects.json` bajo `"integraciones"` (solo las `off`). Un
  nombre o valor desconocido se rechaza listando los válidos. codegraph (`.codegraph/`) y gentle-ai (`.atl/`) se
  detectan en la carpeta del proyecto o en cualquiera de sus repos; engram no se detecta (solo guía condicional).
  Las activas aparecen en `get_context` (una línea + guía para planificar), en `create_task` (la línea) y
  en `update_task(..., "in_progress")` (guía para execute, verify y close); una apagada no aparece nunca.
No cubre renombrar un proyecto ni mover la ubicación de su memoria (`.memorias/<nombre>` o la clave `"memoria"`):
para eso edite `projects.json` a mano y mueva la carpeta con `git mv`/`mv` según corresponda.

## 5. Tareas de código (Claude Desktop → Claude Code)
Flujo: en Claude Desktop se acuerda un cambio y se registra con `create_task` → queda `.project/tasks/T-NNN.md` →
en Claude Code, dentro del repositorio, se ejecuta `/run-task T-NNN` (que empieza con `read_task`) → Claude Code crea la rama, implementa, corre las pruebas
del proyecto ("How to verify") y deja la tarea `in_review` (o `failed`) con el resultado → usted revisa la rama e integra.

Instalación del comando: una sola vez por equipo, con los enlaces globales de la sección 12 (no se copia por repositorio).
Claude Code debe tener el MCP registrado (sección 2) para leer y actualizar la tarea.

Las instrucciones del proyecto en claude.ai (`project_instructions`) ya incluyen el flujo: `create_task` con goal,
criterios verificables, ADR aplicables, archivos y fuera de alcance; el comando `/run-task T-NNN`; `amend_task` para
ampliar una tarea que todavía no corrió; `list_tasks` y `read_task` para revisar; `request_changes` con findings y
criterios adicionales para pedir correcciones; `merged`/`discarded` solo con confirmación del usuario.

`amend_task(project, id, additional_criteria="", notes="")` (ADR-021): solo para tareas `todo` o `changes_requested`
(otro estado → error que lo nombra). Agrega un bloque fechado "### Amendment N" (sub-etiquetas **Additional criteria** y
**Notes**) en la sección "## Amendments" de la spec, antes de "How to verify"; los criterios originales no se tocan. Un
commit por enmienda; al menos uno de los dos campos; una enmienda idéntica dentro de la ventana de idempotencia
(ADR-019) no se escribe de nuevo.

`read_task(project, id)` (ADR-031): brief de trabajo de una tarea en lugar del archivo completo: frontmatter, spec
completa (con las enmiendas), el bloque relevante según el estado (`changes_requested` → la última Review;
`in_review`/`failed` → el último resultado; `in_progress` → la última Review si es el último bloque) y un índice de una
línea (título · rango de líneas · tamaño) de los demás bloques Result/Review, legibles con `read_document` y ese rango.

Ciclo de revisión: `todo` → `in_progress` → `in_review` → (`changes_requested` → `in_progress` → `in_review`)* →
`merged`. Una tarea devuelta se corrige en la misma rama con commits nuevos; cada devolución queda como "Review N" en la
tarea (con **Findings** y **Additional criteria**). `update_task` rechaza pasar de `in_review` a `todo`: devolver es
siempre `request_changes`. El parámetro `status` acepta también (hasta 1.1) los nombres en español de antes del esquema v2
(`pendiente`, `en_curso`, `en_revision`, `fallida`, `integrada`, `descartada`); se guarda y se responde en inglés.

Pendientes que resuelve una tarea (ADR-027): `create_task(..., resolves="P-036, P-037 (partial)")` — ids separados por
coma, cada uno opcionalmente con `(parcial)` o `(partial)` (sin distinguir mayúsculas ni espacios; `p-36` vale como `P-036`). Cada id
debe existir y estar abierto; si alguno no, la herramienta lo rechaza nombrando los inválidos y no escribe nada. Se guarda
en el frontmatter (`resolves: P-036, P-037 (partial)`) y como sección "## Resolves" de la tarea; sin `resolves`, ni
campo ni sección. Al marcar la tarea `merged`, la respuesta recuerda cada pendiente declarado que siga abierto: los completos
con la llamada a `close_pending` y los parciales con cómo registrar lo que falta (P-016): una nota anexada al archivo del
pendiente con `update_document(..., mode="append")`, o cerrarlo con `close_pending` y abrir el resto con `add_pending`. Nunca se cierra ni se modifica un
pendiente automáticamente.

## 6. Ubicación de la memoria
Con la clave `"memoria"` en `projects.json`, la memoria vive fuera del repositorio del código (repo git propio) y no depende
de la rama activa. Recomendado para todos los proyectos. Las herramientas siguen usando rutas `.project/...`.
Las claves de cada proyecto en `projects.json` se leen en español (`ruta`, `memoria`, `escritura`, `pruebas`) o en
inglés (`path`, `memory`, `writable`, `tests`); si están las dos, gana la inglesa. Al escribir se conserva la grafía que
ya tiene la entrada. Renombrar las claves es un paso del instalador (ADR-029), nunca de la migración automática.

## 7. Telemetría
Cada llamada a una herramienta agrega una línea a `logs/uso.jsonl` (herramienta, proyecto, tamaños, duración, error; nunca
el contenido). Resumen: `python3 ~/Projects/.memoria-proyectos/analizar_uso.py --dias 7` (opcional `--proyecto game`).
El script lee el mismo log que escribe el servidor: `--log <ruta>` si se indica, si no `RATIFACT_LOG` (o
`MEMORIA_PROYECTOS_LOG`), y si no `logs/uso.jsonl`. Las filas guardan el nombre inglés de la herramienta; las anteriores
a la v1 (nombre en español) se traducen al agregar, así el historial suma por herramienta. Si el archivo no existe, lo informa con su ruta y termina con error.
`get_context` avisa cuando INDEX.md acumula 5 o más cambios sin regenerarse.
Arranque compacto (ADR-026): `get_context` ya no incluye `OPEN.md`. Después de INDEX.md muestra
"# Open items (N)" con una línea por pendiente abierto (`- P-NNN · <tema> (<fecha>)`, en orden numérico, tema
cortado a 100 caracteres, sin extracto ni dueño) y cierra con `Detail: read_document("<proyecto>", "P-NNN")`; sin
pendientes abiertos, solo "# Open items (0)". "Recently closed" no sale en el arranque. `OPEN.md`
sigue generándose en disco. Al final, la línea "Content language: <content_language> — …" pide escribir el contenido de
los registros en ese idioma (ADR-016); las respuestas de las herramientas son siempre en inglés.
El resumen de `analizar_uso.py` agrega el tamaño de `get_context` por proyecto (p50/máx en caracteres y ~tokens,
con aviso si el p50 supera la referencia de 2.000 tokens = 8.000 caracteres) y la sección "Pendientes abiertos
referenciados por tareas integradas": por proyecto, los declarados en `resolves` y los mencionados en el texto de la
tarea (spec —objetivo, criterios, revisiones— y Result; no cuentan Out of scope, Notes, How to verify ni Resolves),
con la tarea y su fecha de integración. Lee memorias v1 y v2. También cuenta, por proyecto, las rutas v1 traducidas
(`alias_ruta` en el log; ver sección 13).

## 8. Confirmación de decisiones
Toda decisión nace como propuesta. La única vía a "acordada" es `accept_decision`, que exige la frase literal del
usuario (`user_quote`, guardada en el ADR) y debe requerir aprobación en cada cliente:
- Claude Desktop: Configuración → conectores/MCP → memoria-proyectos → `accept_decision` → requiere aprobación.
- Claude Code: `"mcp__memoria-proyectos__accept_decision"` y `"mcp__memoria-proyectos__accept_decisions"` en `permissions.ask` de `.claude/settings.json`.
- Pi: sin permisos configurables; la evidencia queda en la sección "Confirmación" del ADR.

## 9. Revisar propuestas
Desde el chat: "revisa las propuestas pendientes" → `review_proposals` muestra todas con su detalle. Por cada una:
confirmar (`accept_decision`, con aprobación), ajustar (nueva decisión + `supersede_decision`) o descartar
(`reject_decision`, con motivo; queda en el historial como descartada).
Con formularios: "decidamos las propuestas" → `decide_proposals` abre un formulario por propuesta en la aplicación
(accept / reject / adjust / postpone + comment). La respuesta viene directo del usuario, sin pasar por el
modelo. Si la aplicación no soporta formularios (MCP elicitation), la herramienta lo indica y se usa el flujo por chat.

## 10. Aprobaciones en Claude Desktop
Crear registros en la memoria debe pasar por usted; modificar o leer, no. Marque como "requiere aprobación":
`propose_decision`, `add_pending`, `create_task`, `create_document`, `register_project`, `accept_decision` y
`accept_decisions`. Las aprobaciones se guardan por nombre de herramienta: tras la v1 hay que marcarlas de nuevo con los
nombres nuevos (`docs/upgrade-v1.md`).
Deje en "permitir siempre" el resto (lecturas, `read_task`, `amend_task`, `update_document` sobre archivos existentes, `update_task`,
`update_index`, `log_session`, `reject_decision`, `supersede_decision`). El servidor no tiene herramientas
para borrar archivos: nada se elimina, solo cambia de estado. En Claude Code no se usan aprobaciones para el código.

## 11. Pruebas
Desde esta carpeta: `uv run --with pytest --with "mcp>=1.2,<2" pytest -q` (o `python3 -m pytest -q` con pytest y mcp instalados).
Corren contra una carpeta temporal: no tocan `projects.json`, la telemetría ni los proyectos reales.
`test_cobertura.py` falla si se agrega una herramienta sin pruebas (ADR-009, criterio 1).

## 12. /run-task global (una vez por equipo)
`/run-task` es genérico: la fuente es `skills/run-task/SKILL.md` (`run-task.md` es un enlace a ella) y se instala a nivel de usuario con enlaces, así existe en todos los proyectos y se
actualiza solo con el repositorio:
```
mkdir -p ~/.claude/commands ~/.pi/agent/prompts
ln -sf ~/Projects/.memoria-proyectos/run-task.md ~/.claude/commands/run-task.md
ln -sf ~/Projects/.memoria-proyectos/run-task.md ~/.pi/agent/prompts/run-task.md
mkdir -p ~/.codex/skills ~/.agents/skills   # Codex: según la versión lee una u otra carpeta
ln -sfn ~/Projects/.memoria-proyectos/skills/run-task ~/.codex/skills/run-task
ln -sfn ~/Projects/.memoria-proyectos/skills/run-task ~/.agents/skills/run-task
```
`/tarea` (`tarea.md`, `skills/tarea/`) queda como alias deprecado que remite a `/run-task` hasta 1.1, así los enlaces
viejos siguen funcionando.
Si usa gentle-shell independiente, repita el segundo enlace en `~/.gentle-shell/agent/prompts/`.

## 13. Versión de esquema de la memoria

Cada memoria declara en `schema.json` el formato con que fue escrita y el idioma de su contenido:
`{"version": 2, "content_language": "es"}`. Hoy es v2: carpetas `decisions/`, `pending/`, `sessions/`, `tasks/`;
vistas `DECISIONS.md` y `OPEN.md`; claves, estados y títulos de sección en inglés (`docs/v1-english-naming.md` §5–§6).
Las memorias nuevas nacen en v2 con `content_language` `"en"`; las migradas, con `"es"` (ADR-028).

Migración automática (v1 → v2, ADR-028/029/030), en el **primer acceso** a cada memoria (cualquier herramienta con
`project`, también las de solo lectura), bajo el bloqueo:

- Precondiciones: la memoria es un repo git con al menos un commit y `git status` limpio (salvo `.lock`). Si no, la
  herramienta responde un error que explica por qué y no se toca nada.
- Antes de cambiar nada crea el tag `pre-v2` (si existe, `pre-v2-2`, `-3`, …).
- Un solo commit `memory: migrate schema v1 → v2`: renombra las carpetas con `git mv` (historia preservada), cambia
  las claves y los estados del frontmatter, los títulos de sección conocidos y, dentro de los bloques "Revisión N",
  las etiquetas `**Observaciones**`/`**Criterios adicionales**`; regenera `DECISIONS.md`/`OPEN.md` y borra
  `acuerdos.md`/`abiertas.md`. El resto del cuerpo, las citas del usuario, `INDEX.md` y `docs/` no cambian. El cuerpo del
  commit lista lo que quedó como estaba: claves desconocidas y títulos de texto libre.
- Si algo falla (un paso o el commit), la memoria vuelve exactamente al tag (y se borra el tag); la herramienta da el
  error y la próxima llamada lo reintenta.
- Vuelta atrás manual: `git -C <memoria> checkout pre-v2` (o `reset --hard pre-v2`) devuelve el árbol anterior.
- Se mantiene `esquema.json` con `{"version": 2}` como centinela: un servidor anterior a v2 lee "v2" y se niega
  ("usa el esquema v2 y este servidor solo conoce hasta v1"), sin tocar nada. Se quita en 1.1 (ADR-030).
- Despliegue: reinicie todos los clientes (Claude Desktop, Claude Code, Pi, Codex) antes de la primera llamada.
- Rutas v1 (`.project/tareas/T-001.md`, `.project/acuerdos.md`…, que siguen apareciendo en INDEX.md, docs/ y chats
  viejos): se traduce solo el primer tramo después de `.project/` y la respuesta empieza con
  "(→ .project/<ruta nueva>)". Las vistas no se escriben a mano (ni con el nombre viejo ni con el nuevo). Si una memoria
  tiene a la vez la carpeta v1 y la v2, la llamada falla. Cada uso queda en la telemetría (`alias_ruta`); el alias se
  quita en 1.1 cuando `analizar_uso.py` muestre que no se usa.

Una memoria más nueva que el servidor (p. ej. otro equipo con una versión posterior) no se modifica: el servidor pide
actualizar ratifact. `list_projects` muestra la versión de cada memoria.

Para desarrolladores: un cambio de formato sube `VERSION_ESQUEMA` y agrega la función de migración en `MIGRACIONES`
(con los mismos resguardos: repo limpio, tag `pre-vN`, un commit y vuelta atrás), con su prueba en
`tests/test_esquema.py`; la de v2 está en `ratifact/migracion_v2.py` y `tests/test_migracion_v2.py`.

## 14. Codex (CLI, extensión de IDE y app de escritorio)

Las tres comparten `~/.codex/config.toml`. Agregue:

```toml
[mcp_servers.memoria-proyectos]
command = "uv"
args = ["run", "--script", "/home/mano-pc/Projects/.memoria-proyectos/servidor.py"]
startup_timeout_sec = 30   # el primer arranque de uv resuelve dependencias

[mcp_servers.memoria-proyectos.env]
RATIFACT_CONFIG = "/home/mano-pc/Projects/.memoria-proyectos/projects.json"
```

Codex eliminó los comandos personalizados (`~/.codex/prompts`) en marzo de 2026; `/run-task` se instala como skill
(enlaces de carpeta de la sección 12; Codex no sigue un `SKILL.md` enlazado como archivo) y se invoca con `$run-task T-NNN`. Codex lee `AGENTS.md`
de forma nativa, pero solo desde la raíz del repo git hacia abajo: en proyectos de varios repos ponga el bloque en la
carpeta raíz (si abre Codex ahí) y en el `AGENTS.md` de cada repo. Si hay otra memoria de agente instalada (engram),
el servidor declara en sus instrucciones MCP que memoria-proyectos es la fuente de verdad del proyecto.

## 15. Idempotencia de creación (ADR-019)

`propose_decision`, `add_pending` y `create_task` son idempotentes: si ya existe un registro del
mismo tipo (un ADR no compite con una tarea ni con un pendiente, aunque el texto del título coincida) con el
mismo título normalizado (sin distinguir mayúsculas, recortando los extremos y colapsando espacios internos),
**creado en los últimos `VENTANA_IDEMPOTENCIA_MINUTOS` minutos** (10 por defecto) en el mismo proyecto, Y QUE
TODAVÍA ESTÁ EN SU ESTADO INICIAL ("proposed" para ADR, "open" para pendientes, "todo" para tareas),
la llamada no crea ningún archivo nuevo, no hace commit, y devuelve el id del registro existente avisando que
ya estaba registrado (en el caso de una tarea, con el comando `/run-task T-NNN` para repetírselo al usuario).
`amend_task` aplica la misma ventana a una enmienda idéntica de la misma tarea.

La condición de estado inicial es deliberada: un registro que ya cambió de estado (rejected, superseded,
closed, in_progress, in_review, changes_requested, merged, failed, etc.) significa que un humano ya intervino sobre
él, así que nunca cuenta como duplicado aunque sea reciente. Esto cubre el flujo normal de "proponer → el
usuario pide un cambio → descartar/cerrar y volver a registrar corregido", que no debe confundirse con un
reintento perdido (un reintento genuino de un cliente que perdió la respuesta siempre encuentra el registro
todavía en su estado inicial, porque nadie tuvo tiempo de tocarlo).

Esto existe porque la llamada a una tool puede perderse en la capa del cliente (p. ej. Claude Desktop con un
timeout de 120 s) sin que el modelo sepa si el servidor llegó a ejecutarla; con esto, reintentar a ciegas es
seguro. No hay idempotency key del cliente (fuera de alcance v1): la detección es solo por título + estado +
antigüedad. La telemetría registra estas llamadas como exitosas (`error: false`) con un flag `duplicado: true`,
y `analizar_uso.py` reporta cuántas creaciones fueron duplicados detectados.


## 16. Code layout

`servidor.py` es solo el punto de entrada (cabecera PEP 723, agrega su carpeta a `sys.path`, importa el paquete
`ratifact/` y ejecuta `mcp.run()`); los clientes se siguen configurando con `servidor.py` como arriba. El código
vive en `ratifact/` (ADR-020); ningún módulo supera 300 líneas y no hay importaciones circulares:

| Módulo | Responsabilidad |
|---|---|
| `ratifact/app.py` | Instancia FastMCP `mcp`, decoradores `herramienta`/`herramienta_async`, telemetría (`LOG_USO`, `_registrar_uso`) y `_ejecutar`. |
| `ratifact/config.py` | Rutas y configuración: `CONFIG` (projects.json, claves en español o inglés: `_valor`, `_clave_escritura`), `BASE_PROYECTOS`, `ErrorMemoria`, `_proyectos`, `_raiz`, `_mem`, ayudantes de repositorios, `_ruta_segura`, `_zonas_escritura` y el alias de rutas v1 (`_traducir_alias`). |
| `ratifact/vocabulario.py` | Vocabulario del esquema v2 y su equivalente v1: carpetas, vistas, claves, estados por tipo y `_normalizar_estado` (parámetros en español o inglés); mapas del contrato v0 → v1 (`HERRAMIENTAS_V0`, `PARAMETROS_V0`, `PROMPTS_V0`, `MODOS_V0`). |
| `ratifact/esquema.py` | `VERSION_ESQUEMA`, `MIGRACIONES`, versión (`schema.json` / centinela `esquema.json`), resguardos de la migración (repo limpio, tag, commit, vuelta atrás), `_asegurar_esquema` (primer acceso) y `_bloqueo`. |
| `ratifact/migracion_v2.py` | Migración v1 → v2: carpetas, frontmatter, títulos, etiquetas de revisión y el informe del commit. |
| `ratifact/registros.py` | Frontmatter (lectura/escritura), `_escribir_atomico`, `_commit`, ids y slugs, idempotencia (ADR-019), `_regenerar_vistas`, `_resumen_tareas`, `_hoy`/`_ahora`. |
| `ratifact/catalogo.py` | Catálogo de la memoria derivado en cada llamada (ADR-022): `_catalogo`, resolución de ids de `read_document` (`_resolver_id`), registros de `list_documents` y coincidencias por id/título de `search` (id exacto y hasta 5 títulos al inicio de palabra) y el bloque de pendientes abiertos de `get_context` (`_bloque_pendientes`, ADR-026). Sin índice, caché ni watcher. |
| `ratifact/busqueda.py` | Respuesta de `search` con cuotas por sección: catálogo, luego memoria y código a partes iguales (lo que un lado no usa pasa al otro), y la línea final con lo omitido por sección. |
| `ratifact/listado.py` | Listado con profundidad adaptativa de `list_documents` (ADR-023): `_listado` (presupuesto `LIMITE_LISTADO_ENTRADAS`/`LIMITE_LISTADO_CARACTERES` en config). |
| `ratifact/plantillas.py` | `PLANTILLA_INSTRUCCIONES`, `PLANTILLA_AGENTES` y `TEXTO_CIERRE`. |
| `ratifact/prompts.py` | Prompts `start` y `close` (antes `inicio` y `cierre`). |
| `ratifact/integraciones/` | Integraciones opcionales (ADR-024, ADR-025): `base.py` (descriptor `Integracion`, `FASES`), un módulo por integración (`codegraph.py`, `gentle_ai.py`, `engram.py`) y `registro.py` (`INTEGRACIONES`, detección en disco en cada llamada, guía para `get_context`/`create_task`/`update_task` y el parseo de `integraciones`). Agregar una = un módulo + registrarlo. Nunca llama a otros MCP. |
| `ratifact/herramientas/contexto_documentos.py` | `list_projects`, `get_context`, `search`, `list_documents`, `read_document`, `create_document`, `update_document`, `update_index`. |
| `ratifact/herramientas/decisiones.py` | `propose_decision`, `accept_decision`, `accept_decisions`, `review_proposals`, `decide_proposals`, `reject_decision`, `supersede_decision`. |
| `ratifact/herramientas/pendientes_sesiones.py` | `add_pending`, `close_pending`, `log_session`. |
| `ratifact/herramientas/tareas.py` | `create_task`, `update_task`, `request_changes`, `list_tasks` (y `_comando_pruebas`). |
| `ratifact/herramientas/tareas_brief.py` | `amend_task` (ADR-021) y `read_task` (ADR-031). |
| `ratifact/herramientas/proyectos.py` | `init_memory`, `project_instructions`, `register_project`, `update_project` y la detección del comando de pruebas. |

`tests/contrato_herramientas.json` es la instantánea del contrato MCP (nombre, descripción y esquema de cada
herramienta y prompt); `tests/test_contrato.py` falla si cambia. `tests/contrato_herramientas_v0.json` es la
instantánea anterior al renombrado (v0, en español): la prueba comprueba que cada herramienta vieja tiene exactamente
una nueva y que `amend_task`/`read_task` son las únicas agregadas.
