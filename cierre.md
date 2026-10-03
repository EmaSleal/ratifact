---
description: Cierra la sesión: registra decisiones, pendientes y bitácora, y regenera INDEX.md
---

Haz el cierre de esta sesión del proyecto `game` con las herramientas de memoria-proyectos:

1. Repasa la conversación y lista lo que se resolvió y lo que quedó abierto.
2. Decisiones nuevas: regístralas con `registrar_decision` como **propuesta**, salvo las que yo haya
   confirmado explícitamente en esta conversación (esas, `acordada=True`). Si una reemplaza a otra, usa `reemplazar_decision`.
3. Temas sin resolver: `registrar_pendiente`. Pendientes resueltos: `cerrar_pendiente` (con el ADR si aplica).
4. `registrar_sesion` con un resumen breve (5–10 líneas): qué se hizo, qué se decidió, qué sigue.
5. Regenera `INDEX.md` con `actualizar_indice`: un RESUMEN del estado real del proyecto (qué es, estado por hito/fase,
   foco actual, próximos pasos, dónde está cada cosa). Reescríbelo completo; no agregues líneas al anterior. Antes,
   contrasta con `obtener_contexto("game")`, `listar_tareas` y los acuerdos vigentes.
6. Termina con una lista de lo que registraste (ids) y las propuestas que esperan mi confirmación.
No inventes decisiones: si algo es ambiguo, déjalo como pendiente o pregúntame.
