---
name: tarea
description: Ejecuta una tarea de código registrada en memoria-proyectos (ej. /tarea T-001, o $tarea T-001 en Codex). Úsala solo cuando el usuario pide ejecutar una tarea T-NNN; no la uses para tareas sin id.
argument-hint: T-NNN
---

Ejecuta la tarea **$ARGUMENTS** del proyecto de este repositorio.
(Si arriba ves el texto literal `$ARGUMENTS` —p. ej. en Codex, donde esto es una skill—, la tarea es el `T-NNN` que escribió el usuario en su mensaje; úsalo en cada lugar donde aparezca `$ARGUMENTS`. Si no indicó ninguno, pregúntale cuál.)

## 0. Identificar el proyecto
El nombre del proyecto en `memoria-proyectos` está en el `CLAUDE.md` / `AGENTS.md` de este repositorio ("con el proyecto `<nombre>`"). Si no lo encuentras, llama `listar_proyectos` y elige el proyecto cuya ruta contiene el directorio actual (en proyectos de varios repos, la ruta es la carpeta que los agrupa); si sigue sin estar claro, pregúntame. En adelante, `<proyecto>` es ese nombre.

## 1. Preparar
1. Lee la especificación con la herramienta MCP `memoria-proyectos` → `leer_documento("<proyecto>", "$ARGUMENTS")` con el id (p. ej. `leer_documento("<proyecto>", "T-007")`: resuelve el archivo real y lo indica en la primera línea). Si el id no existe, usa `listar_tareas("<proyecto>")` para encontrar la tarea.
2. Según su estado:
   - `pendiente`: primera ejecución.
   - `devuelta`: el usuario revisó una ejecución anterior y pide correcciones. Lee la **última** sección "Revisión N" del Resultado: sus observaciones y criterios adicionales se suman a los criterios originales, que siguen vigentes. Lo que la revisión aprueba no se rehace.
   - `fallida`: reintento; lee el último resultado para saber qué falló.
   - Cualquier otro estado: detente y avísame.

   Si la spec trae el campo `repositorio` (proyectos de varios repos), **todo lo que sigue —git, ramas, comandos y pruebas— se hace dentro de esa carpeta**, no en la raíz del proyecto.
3. Lee las decisiones listadas en "Decisiones aplicables" (`.project/decisiones/`). Solo las **acordadas** son reglas.
4. Verifica con `git status` que el árbol de trabajo esté limpio. Si hay cambios sin commitear, **detente** y pregúntame; no los muevas ni los descartes.
5. Rama (campo `rama` de la spec). Comprueba si ya existe con `git branch --list <rama>`:
   - **Ya existe** (siempre en `devuelta`, y a menudo en `fallida`): `git switch <rama>` y continúa sobre ella. No la recrees, no la rebases ni hagas `--amend` sobre commits anteriores: las correcciones van en commits nuevos.
   - **No existe:** créala **desde la rama principal** del repositorio (`main`, o `master` si no existe `main`): `git switch <principal> && git switch -c <rama>`.
   - Si la spec indica trabajar sobre otra rama existente, cámbiate a esa y no crees otra.
6. Marca la tarea: `actualizar_tarea("<proyecto>", "$ARGUMENTS", "en_curso")`.

## 2. Ejecutar
- Puedes apoyarte en el orquestador, los sub-agentes y las skills de tu entorno (p. ej. gentle-ai) para implementar; la spec define el contrato y los criterios de aceptación, no el método. Aprendizajes técnicos pueden ir a la memoria del agente (p. ej. engram); decisiones nuevas NO: proponlas al usuario para registrarlas en memoria-proyectos.
- Implementa **solo** lo que pide la spec. Lo que esté en "Fuera de alcance" no se toca.
- Si la spec es ambigua o contradice un ADR acordado, **detente y pregúntame** antes de decidir por tu cuenta.
- Respeta las reglas del `CLAUDE.md` / `AGENTS.md` del repositorio.
- Agrega o ajusta pruebas que cubran cada criterio de aceptación verificable.

## 3. Verificar
Ejecuta el comando de la sección **"Cómo verificar"** de la spec, desde la raíz del repositorio, y guarda el resumen (pasan/fallan por suite). Si la spec no trae comando, usa el del `CLAUDE.md` / `AGENTS.md`; si tampoco hay, pregúntame antes de dar la tarea por verificada. Repasa cada criterio de aceptación y marca cuál se cumple y cómo se verificó.

## 4. Cerrar
- **Pruebas en verde y criterios cumplidos:** haz commit en la rama (`T-NNN: <título>`; en una tarea devuelta, `T-NNN: correcciones de la revisión N`) y llama
  `actualizar_tarea("<proyecto>", "$ARGUMENTS", "en_revision", resultado=..., commit=<sha corto>)`.
- **Algo falla y no se resuelve dentro del alcance:** haz commit del avance igualmente y llama `actualizar_tarea(..., "fallida", resultado=...)` explicando qué falla y por qué.
- El `resultado` incluye: archivos tocados, pruebas ejecutadas con su conteo (pasan/fallan), criterio por criterio, y cualquier desvío respecto de la spec. En una tarea devuelta, recorre también cada criterio adicional de la revisión.
- **No hagas merge a otra rama** ni marques la tarea como `integrada`: eso lo decido yo después de revisar.
- **Nunca muevas, restaures, reescribas ni borres la rama principal ni ninguna rama que no sea la de la tarea** (nada de `git branch -f`, `git reset` sobre otras ramas, `git push --force` ni `git branch -D`), aunque veas que cambiaron mientras trabajabas: pudo haberlas integrado yo. Si notas un cambio inesperado, solo repórtalo en el `resultado`.
