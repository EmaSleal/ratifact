# ratifact (antes memoria-proyectos) — instalación

English: [README.md](README.md) (qué es, instalación, primer proyecto, /run-task, comandos, integraciones, upgrade).

Servidor MCP local: comando `ratifact serve` (paquete instalable, sección 0; `servidor.py` es su envoltorio hasta 1.1). Proyectos registrados: `projects.json`.
Desde la v1 (T-011) el contrato está en inglés: herramientas, parámetros, descripciones y respuestas
(`docs/v1-english-naming.md`). Pasos para usuarios existentes después de actualizar: `docs/upgrade-v1.md`.

Variables de entorno: `RATIFACT_CONFIG` (projects.json), `RATIFACT_LOG` (telemetría) y `RATIFACT_BASE` (carpeta de
proyectos). Las anteriores `MEMORIA_PROYECTOS_*` siguen funcionando como respaldo hasta 1.1 (gana la nueva; el log del
servidor avisa una vez por variable). Sin variable, la configuración es `~/.config/ratifact/projects.json` si existe, si
no `~/.config/memoria-proyectos/projects.json` (no se mueve ni reescribe nada).

## 0. Comando `ratifact` (instalación fija)
Desde T-012 el repositorio es un paquete instalable (`pyproject.toml`, MIT). `uv tool install ratifact` (desde PyPI) o
`uv tool install ~/Projects/.memoria-proyectos` (desde la copia local) instala una copia fija (no editable) y deja el
ejecutable `~/.local/bin/ratifact`; después de cada integración en main: `uv tool install --reinstall
~/Projects/.memoria-proyectos` y reiniciar los clientes. Los clientes se configuran con `ratifact install --apply`
(T-013, sección 1); las configuraciones viejas con `servidor.py` siguen funcionando hasta 1.1.

| Subcomando | Qué hace |
|---|---|
| `ratifact serve` | Servidor MCP por stdio (lo que lanzan los clientes). `servidor.py` es un envoltorio de esto hasta 1.1. |
| `ratifact install [--apply] [--client NOMBRE]` | Configura los clientes MCP que encuentra (Claude Desktop, Claude Code, Pi, Codex) y enlaza `/run-task` (sección 1). Sin `--apply` solo muestra el plan. |
| `ratifact report [--days N] [--project P] [--log RUTA]` | Resumen del uso (sección 7). `analizar_uso.py` es un envoltorio hasta 1.1 (acepta `--dias`/`--proyecto`). |
| `ratifact doctor` | Solo lectura: versión y de dónde corre (instalación fija o copia de trabajo, con aviso — P-017), configuración usada y grafía de sus claves, por proyecto código, memoria (ruta, esquema, `.memorias/` viejo o `.ratifact/` nuevo, estado git) e integraciones detectadas, log, variables `MEMORIA_PROYECTOS_*` y acciones pendientes, y el estado de cada cliente (configurado con ratifact / configuración vieja / sin configurar / no encontrado). Sale con 0 si no hay nada pendiente, 1 si hay acciones. Si no existe la configuración por defecto pero hay servidores corriendo con `RATIFACT_CONFIG`/`MEMORIA_PROYECTOS_CONFIG` o un `projects.json` junto al repositorio de origen, sugiere el comando exacto (`RATIFACT_CONFIG=<ruta> ratifact upgrade`). |
| `ratifact upgrade` | Paso explícito de ADR-029 con todos los clientes cerrados. Sin opciones solo muestra el plan; `--apply` lo ejecuta: migra a v2 las memorias v1, mueve `<base>/.memorias/<p>` a `<base>/.ratifact/<p>` (las rutas propias nunca se mueven), escribe `~/.config/ratifact/projects.json` con claves en inglés y renombra el viejo a `projects.json.bak-v1`, regenera las vistas y copia el log viejo. Aborta si hay un servidor corriendo con esa configuración, un `.lock` tomado o una memoria con cambios sin commit (cabecera "Aborted — nothing was changed:", el plan y los motivos; código de salida 1); idempotente; si un paso falla, lo revierte. |
| `ratifact --version` | Versión instalada. |

## 1. Clientes MCP: `ratifact install`
Una vez por equipo, con el comando instalado (sección 0):

```
ratifact install            # plan: qué clientes encontró y qué cambiaría; no toca nada
ratifact install --apply    # lo hace, con respaldo de cada archivo
```

Configura los clientes que encuentra: Claude Desktop (`~/.config/Claude/claude_desktop_config.json`; en macOS
`~/Library/Application Support/Claude/claude_desktop_config.json`), Claude Code (`claude mcp add --scope user` si existe
el comando `claude`; si no, `~/.claude.json`), Pi (`~/.pi/agent/mcp.json`) y Codex (`~/.codex/config.toml`). Cada uno
queda con el servidor `ratifact`, comando = ruta absoluta del ejecutable instalado, `args ["serve"]` y sin variables de
entorno; el resto del archivo (otros MCP, preferencias) queda idéntico. Antes de escribir guarda
`<archivo>.bak-ratifact-<fecha>` junto al archivo (los archivos dentro de un proyecto —`CLAUDE.md`, `AGENTS.md`,
`.claude/settings.json`— se respaldan en `~/.local/state/ratifact/backups/<fecha>/<ruta absoluta>`, nunca dentro del
repositorio; un archivo que no se reescribe no tiene respaldo), valida el resultado volviéndolo a parsear y reemplaza el original de forma atómica; un
archivo inválido (p. ej. una coma de más en el JSON) se informa y no se toca. Un cliente no instalado se informa y se
salta; `--client claude-desktop|claude-code|pi|codex` limita a uno. Un segundo `--apply` no cambia nada y lo dice.

Además: reemplaza la entrada vieja `memoria-proyectos` (nunca quedan las dos), renombra los permisos de Claude Code
`mcp__memoria-proyectos__<herramienta>` → `mcp__ratifact__<herramienta>` (en `~/.claude/settings.json` y en el
`.claude/settings.json` de cada proyecto registrado; los nombres en español de v0 se traducen), mueve las tablas de
aprobación por herramienta de Codex a la clave nueva, reescribe el bloque generado de `CLAUDE.md`/`AGENTS.md` de los
proyectos registrados (solo ese texto exacto, con respaldo fuera del repositorio), enlaza `/run-task` (sección 12), crea
`~/.config/ratifact/projects.json` vacío si no hay ninguna configuración, informa las integraciones detectadas por
proyecto y cómo apagarlas (sin preguntar, ADR-025) y lista lo que no puede hacer solo (las aprobaciones de Claude
Desktop, sección 10). Reinicie los clientes después.

## Nota de versión
El servidor fija `mcp>=1.2,<2`. La serie 2.x de la librería `mcp` cambió la API y el servidor se desconecta al
arrancar. No quite ese límite sin probar antes con `./diagnostico.sh`.

## 2. Claude Code
Lo configura `ratifact install --apply` (sección 1): equivale a
`claude mcp add --scope user ratifact -- <home>/.local/bin/ratifact serve`.

## 3. Instrucciones del proyecto en claude.ai
El texto exacto (en inglés, con los nombres de herramientas v1) lo devuelve `project_instructions("<proyecto>")`:
péguelo tal cual en *Project instructions*. Empieza así:

> project: game
> At the start of every chat, call `get_context("game")` before answering; assume nothing that is not there.
> When we reach a decision, record it with `propose_decision` (it stays proposed). Only if I accept it explicitly, call `accept_decision` with my literal words in `user_quote`; the app will ask me to approve it.
> …

## 4. Agregar otro proyecto
En cualquier chat con el MCP conectado, pida: "registra el proyecto <nombre> con el código en <ruta>".
`register_project` lo agrega a `projects.json`, crea su memoria (por defecto en `~/Projects/.ratifact/<nombre>`,
con repo git propio) y devuelve las instrucciones exactas para pegar en el proyecto de Claude y en CLAUDE.md/AGENTS.md.
Para recuperar esas instrucciones de un proyecto existente: `project_instructions("<nombre>")`.
Recomendado: marcar `register_project` como "requiere aprobación" igual que `accept_decision`.

### Actualizar un proyecto ya registrado

`update_project(name, path="", tests="", repo="", redetect=False, integrations="", models="")` corrige projects.json sin
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
- `models`: excepciones del proyecto a los modelos por rol, p. ej. `"explore=haiku,write=sonnet"` (roles
  `explore`, `write`, `verify`; el valor es el nombre de modelo del cliente, texto libre). `inherit` en un rol quita
  la excepción de ese rol, que vuelve a usar el global. Un rol desconocido o un valor vacío se rechazan listando los
  roles válidos. Se guarda en la entrada del proyecto en `projects.json` bajo `"models"`.

### Modelos por rol (`settings.json`)

El valor global de los modelos por rol vive en `settings.json`, en la misma carpeta que el `projects.json` activo
(p. ej. `~/.config/ratifact/settings.json`). Lo crea el usuario a mano (`ratifact install` no lo escribe):

```json
{"models": {"explore": "haiku", "write": "sonnet", "verify": "sonnet"}}
```

Se lee en cada llamada. Las excepciones de un proyecto (`update_project(..., models=...)`) ganan rol por rol; los
roles que el proyecto no define se heredan del global. Si hay al menos un rol configurado,
`update_task(..., "in_progress")` agrega un bloque "Model routing" con cada rol, su modelo y su origen
(global/project): es la petición explícita del usuario de fijar ese modelo al delegar el rol a un sub-agente; un
cliente que no permite elegir el modelo de sub-agentes lo ignora, y los roles sin modelo usan el de la sesión. Sin
configuración la respuesta no cambia. Un `settings.json` inválido no rompe ninguna herramienta (se ignora con un
aviso en ese bloque) y `ratifact doctor` lo reporta sin modificarlo; doctor muestra además los modelos efectivos de
cada proyecto (o `models: session default`).
No cubre renombrar un proyecto ni mover la ubicación de su memoria (`.ratifact/<nombre>` o la clave `"memoria"`):
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
Sin esa clave, la memoria es `<carpeta de proyectos>/.ratifact/<nombre>` (desde T-012); una que todavía vive en la
ruta por defecto vieja `.memorias/<nombre>` se sigue encontrando ahí hasta que `ratifact upgrade --apply` la mueve.
Las claves de cada proyecto en `projects.json` se leen en español (`ruta`, `memoria`, `escritura`, `pruebas`,
`integraciones`) o en inglés (`path`, `memory`, `writable`, `tests`, `integrations`); si están las dos, gana la inglesa.
Al escribir se conserva la grafía que ya tiene la entrada. Renombrar las claves y mover las memorias de `.memorias/` a
`.ratifact/` es `ratifact upgrade --apply` (ADR-029, sección 0), nunca la migración automática.

## 7. Telemetría
Cada llamada a una herramienta agrega una línea a `~/.local/state/ratifact/uso.jsonl` (`$XDG_STATE_HOME/ratifact/`; hasta
T-012 era `<repo>/logs/uso.jsonl`, y `ratifact upgrade` lo copia si el nuevo no existe) con herramienta, proyecto,
tamaños, duración y error; nunca el contenido. Resumen: `ratifact report --days 7` (opcional `--project game`; también
`python3 ~/Projects/.memoria-proyectos/analizar_uso.py --dias 7` hasta 1.1).
El informe lee el mismo log que escribe el servidor: `--log <ruta>` si se indica, si no `RATIFACT_LOG` (o
`MEMORIA_PROYECTOS_LOG`), y si no `~/.local/state/ratifact/uso.jsonl`. Las filas guardan el nombre inglés de la herramienta; las anteriores
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
- Claude Desktop: Configuración → conectores/MCP → ratifact → `accept_decision` → requiere aprobación.
- Claude Code: `"mcp__ratifact__accept_decision"` y `"mcp__ratifact__accept_decisions"` en `permissions.ask` de `.claude/settings.json` (`ratifact install` renombra los `mcp__memoria-proyectos__…` existentes).
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
`accept_decisions`. Las aprobaciones se guardan por nombre de servidor y de herramienta: tras pasar a la clave
`ratifact` (T-013) hay que marcarlas de nuevo; `ratifact install` lo recuerda en sus pasos manuales.
Deje en "permitir siempre" el resto (lecturas, `read_task`, `amend_task`, `update_document` sobre archivos existentes, `update_task`,
`update_index`, `log_session`, `reject_decision`, `supersede_decision`). El servidor no tiene herramientas
para borrar archivos: nada se elimina, solo cambia de estado. En Claude Code no se usan aprobaciones para el código.

## 11. Pruebas
Desde esta carpeta: `uv run --with pytest --with "mcp>=1.2,<2" pytest -q` (o `python3 -m pytest -q` con pytest y mcp instalados).
Corren contra una carpeta temporal: no tocan `projects.json`, la telemetría ni los proyectos reales.
`test_cobertura.py` falla si se agrega una herramienta sin pruebas (ADR-009, criterio 1).

## 12. /run-task global (una vez por equipo)
`/run-task` es genérico: la fuente es `ratifact/skills/run-task/SKILL.md`, que viaja dentro del paquete instalado
(`skills/` y `run-task.md` en la raíz del repositorio son enlaces a ella). `ratifact install --apply` lo enlaza desde la
copia instalada (nunca desde la copia de trabajo), así existe en todos los proyectos:

- Claude Code: `~/.claude/commands/run-task.md`
- Pi: `~/.pi/agent/prompts/run-task.md` (y `~/.pi/agent/skills/run-task` si existe esa carpeta)
- Codex: `~/.codex/skills/run-task` y `~/.agents/skills/run-task` (según la versión lee una u otra; se enlaza la carpeta
  entera porque Codex no sigue un `SKILL.md` enlazado como archivo)

`/tarea` (`ratifact/skills/tarea/`) queda como alias deprecado que remite a `/run-task` hasta 1.1 y se enlaza igual.
Un destino que ya existe como archivo o carpeta real (no enlace) nunca se reemplaza: el plan pide borrarlo a mano.
Si usa gentle-shell independiente, enlace también `~/.gentle-shell/agent/prompts/run-task.md` a la misma fuente.

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

Las tres comparten `~/.codex/config.toml`; lo configura `ratifact install --apply` (sección 1) con una edición acotada:
solo reescribe las tablas `[mcp_servers.memoria-proyectos]`/`[mcp_servers.ratifact]` y sus subtablas (borra la `.env`,
renombra las `.tools.<herramienta>` con su `approval_mode`) y deja el resto del archivo byte por byte. Queda:

```toml
[mcp_servers.ratifact]
command = "<home>/.local/bin/ratifact"
args = ["serve"]
```

Si el servidor está definido de otra forma (tabla en línea, claves con puntos), no toca el archivo y da las
instrucciones para hacerlo a mano.

Codex eliminó los comandos personalizados (`~/.codex/prompts`) en marzo de 2026; `/run-task` se instala como skill
(enlaces de carpeta de la sección 12; Codex no sigue un `SKILL.md` enlazado como archivo) y se invoca con `$run-task T-NNN`. Codex lee `AGENTS.md`
de forma nativa, pero solo desde la raíz del repo git hacia abajo: en proyectos de varios repos ponga el bloque en la
carpeta raíz (si abre Codex ahí) y en el `AGENTS.md` de cada repo. Si hay otra memoria de agente instalada (engram),
el servidor declara en sus instrucciones MCP que ratifact es la fuente de verdad del proyecto.

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

`servidor.py` es solo un envoltorio de `ratifact serve` hasta 1.1 (cabecera PEP 723, agrega su carpeta a `sys.path`,
importa el paquete `ratifact/` y llama a `ratifact.cli`); el punto de entrada es el comando `ratifact` (sección 0). El código
vive en `ratifact/` (ADR-020); ningún módulo supera 300 líneas y no hay importaciones circulares:

| Módulo | Responsabilidad |
|---|---|
| `ratifact/cli.py` | Comando `ratifact` (`serve`, `install`, `report`, `doctor`, `upgrade`, `--version`); `servidor()` carga herramientas y prompts. |
| `ratifact/instalar.py`, `ratifact/instalar_extras.py` | `ratifact install` (T-013): plan y ejecución; permisos de Claude Code, bloque de CLAUDE.md/AGENTS.md y enlaces de `/run-task`. |
| `ratifact/clientes.py`, `ratifact/clientes_toml.py` | Clientes MCP (Claude Desktop, Claude Code, Pi, Codex): detección, estado (también para doctor) y edición de su configuración; la de Codex es una edición acotada del TOML. |
| `ratifact/archivos.py` | Escritura segura de archivos de otros programas: validación, respaldo `.bak-ratifact-<fecha>` y reemplazo atómico. |
| `ratifact/skills/` | Skills `run-task` y `tarea` (alias hasta 1.1), incluidas en el paquete. |
| `ratifact/rutas.py` | Rutas sin projects.json: configuración nueva/vieja, log por defecto (XDG), copia de trabajo o instalación fija y repositorio de origen. |
| `ratifact/informe.py`, `ratifact/informe_memoria.py` | `ratifact report` (antes `analizar_uso.py`): agregados del log y los indicadores que salen de las memorias. |
| `ratifact/instalacion.py` | Inventario de solo lectura para doctor/upgrade: projects.json y sus claves, memorias (ubicación, esquema, git), integraciones, servidores en marcha y `.lock` tomados. |
| `ratifact/doctor.py` | `ratifact doctor`. |
| `ratifact/upgrade.py`, `ratifact/upgrade_aplicar.py` | `ratifact upgrade`: plan (sin cambios) y ejecución por pasos con vuelta atrás. |
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
