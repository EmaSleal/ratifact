---
description: Ejecuta una tarea registrada en la memoria del proyecto (ej. /tarea T-001)
argument-hint: T-NNN
---

Ejecuta la tarea **$ARGUMENTS** del proyecto `game`.

## 1. Preparar
1. Lee la especificación con la herramienta MCP `memoria-proyectos` → `leer_documento("game", ".project/tareas/<archivo de $ARGUMENTS>")` (usa `listar_tareas("game")` si no conoces el nombre exacto). Si el MCP no está disponible, lee `../.project/tareas/$ARGUMENTS-*.md`.
2. Si su estado no es `pendiente` ni `fallida`, detente y avísame.
3. Lee las decisiones listadas en "Decisiones aplicables" (`.project/decisiones/`). Solo las **acordadas** son reglas.
4. Verifica con `git status` que el árbol de trabajo esté limpio. Si hay cambios sin commitear, **detente** y pregúntame; no los muevas ni los descartes.
5. Crea la rama indicada en el campo `rama` de la spec **desde `main`**: `git switch main && git switch -c <rama>`. Excepción: si la spec indica trabajar sobre una rama existente, cámbiate a esa rama (`git switch <rama existente>`) y no crees otra.
6. Marca la tarea: `actualizar_tarea("game", "$ARGUMENTS", "en_curso")`.

## 2. Ejecutar
- Puedes apoyarte en el orquestador, los sub-agentes y las skills de gentle-ai para implementar; la spec define el contrato y los criterios de aceptación, no el método. Aprendizajes técnicos van a engram; decisiones nuevas NO: proponlas al usuario para registrarlas en memoria-proyectos.
- Implementa **solo** lo que pide la spec. Lo que esté en "Fuera de alcance" no se toca.
- Si la spec es ambigua o contradice un ADR acordado, **detente y pregúntame** antes de decidir por tu cuenta.
- Respeta `CLAUDE.md`: la simulación (`src/sim`) sin nodos; los valores numéricos en `data/*.json`.
- Agrega o ajusta pruebas que cubran cada criterio de aceptación verificable.

## 3. Verificar
Ejecuta todas las suites desde la raíz del repositorio y guarda el resumen de cada una:
```
godot --headless --path . -s res://tests/run_tests.gd
godot --headless --path . -s res://tests/run_tests_hito1.gd
```
(Más cualquier `tests/run_tests_*.gd` nuevo.) Repasa cada criterio de aceptación y marca cuál se cumple y cómo se verificó.

## 4. Cerrar
- **Pruebas en verde y criterios cumplidos:** haz commit en la rama (`T-NNN: <título>`) y llama
  `actualizar_tarea("game", "$ARGUMENTS", "en_revision", resultado=..., commit=<sha corto>)`.
- **Algo falla y no se resuelve dentro del alcance:** haz commit del avance igualmente y llama `actualizar_tarea(..., "fallida", resultado=...)` explicando qué falla y por qué.
- El `resultado` incluye: archivos tocados, pruebas ejecutadas con su conteo (pasan/fallan), criterio por criterio, y cualquier desvío respecto de la spec.
- **No hagas merge a otra rama** ni marques la tarea como `integrada`: eso lo decido yo después de revisar.
- **Nunca muevas, restaures, reescribas ni borres `main` ni ninguna rama que no sea la de la tarea** (nada de `git branch -f`, `git reset` sobre otras ramas, `git push --force` ni `git branch -D`), aunque veas que cambiaron mientras trabajabas: pudo haberlas integrado yo. Si notas un cambio inesperado, solo repórtalo en el `resultado`. (P-012)
