"""Memoria de esquema v1 (carpetas, claves, estados y títulos en español) para las pruebas de la migración v1 → v2.
Reúne las formas reales encontradas en las cuatro memorias del usuario (inventario de T-010): títulos fijos y con
fecha, bloques de revisión con sus etiquetas, una línea del cuerpo con forma `clave: valor` (erp T-008), etiquetas en
negrita escritas por agentes, títulos de texto libre y una clave de frontmatter desconocida."""
from __future__ import annotations

import subprocess
from pathlib import Path

ARCHIVOS = {
    ".gitignore": ".lock\n*.tmp\n",
    "esquema.json": '{"version": 1}\n',
    "INDEX.md": "# demo\n\nEstado actual: ver decisiones/ADR-001-usar-godot.md y .project/tareas/T-001.\n",
    "docs/notas.md": "# Notas\n\nestado: acordada (texto, no frontmatter)\n",
    "acuerdos.md": "# Acuerdos\n\n(vista v1)\n",
    "abiertas.md": "# Decisiones abiertas\n\n(vista v1)\n",
    "decisiones/ADR-001-usar-godot.md": """---
id: ADR-001
titulo: Usar Godot
estado: acordada
fecha: 2026-10-01
creado: 2026-10-01T10:00:00
resumen: Motor Godot 4
confirmada: 2026-10-02
---
# ADR-001 — Usar Godot

## Decisión
Usamos Godot 4.

## Justificación
Ligero.

## Alternativas consideradas
Unity.

## Confirmación (2026-10-02)
> "sí, Godot"

## Confirmación (2026-10-03, en lote)
> "ok todas"
""",
    "decisiones/ADR-002-usar-unity.md": """---
id: ADR-002
titulo: Usar Unity
estado: descartada
fecha: 2026-10-01
resumen: Unity
descartada: 2026-10-02
---
# ADR-002 — Usar Unity

## Decisión
Unity.

## Justificación
Popular.

## Descartada (2026-10-02)
Licencia.
""",
    "decisiones/ADR-003-motor-propio.md": """---
id: ADR-003
titulo: Motor propio
estado: reemplazada
fecha: 2026-10-01
resumen: Propio
reemplazada_por: ADR-001
---
# ADR-003 — Motor propio

## Decisión
Propio.

## Justificación
Control.
""",
    "decisiones/ADR-004-licencia.md": """---
id: ADR-004
titulo: Licencia MIT
estado: propuesta
fecha: 2026-10-04
resumen: MIT
prioridad: alta
---
# ADR-004 — Licencia MIT

## Decisión
MIT.

## Justificación
Simple.
""",
    "pendientes/P-001-elegir-arte.md": """---
id: P-001
tema: Elegir arte
estado: abierta
fecha: 2026-10-01
dueno: Emanuel
---
Pixel art o 3D.
""",
    "pendientes/P-002-elegir-musica.md": """---
id: P-002
tema: Elegir música
estado: cerrada
fecha: 2026-10-01
creado: 2026-10-01T09:00:00
cerrado: 2026-10-05
resolucion: Chiptune (ADR-001)
---
Qué estilo.

## Resolución (2026-10-05)
Chiptune.
""",
    "tareas/T-001-sincronizacion.md": """---
id: T-001
titulo: Sincronización diaria
estado: integrada
fecha: 2026-10-01
rama: t-001-sincronizacion
repositorio: backend
resuelve: P-001 (parcial)
actualizada: 2026-10-06
commit: abc1234
revisiones: 1
---
# T-001 — Sincronización diaria

## Objetivo
Sincronizar.
nuevos: ProveedorTipoCambio, HaciendaTipoCambioClient, TipoCambioSyncService (+ tests)
estado: pendiente

## Criterios de aceptación
1. Funciona.

## Resuelve
- P-001 (parcial) · Elegir arte

## Decisiones aplicables
ADR-001

## Archivos involucrados
src/x.py

## Fuera de alcance
Nada.

## Notas
**Observaciones**
fuera de un bloque de revisión: no se migra

## Cómo verificar
Desde la raíz: `pytest`

## Resultado
### 2026-10-04 · en_revision
**Criterios:** todos
**Archivos:** src/x.py

### Revisión 1 · 2026-10-05 · devuelta
Corregir en la MISMA rama `t-001-sincronizacion` (sobre el commit abc1234), con commits nuevos; los criterios originales siguen vigentes.

**Observaciones**
Falta un caso.
**Observaciones:**
con dos puntos: no es la etiqueta generada

**Criterios adicionales**
A. el caso.

## Ejecución 2 (commit def5678)
Hecho.

### 2026-10-06 · integrada
Listo.
""",
    "tareas/T-002-pendiente.md": """---
id: T-002
titulo: Tarea nueva
estado: pendiente
fecha: 2026-10-07
creado: 2026-10-07T10:00:00
rama: t-002-tarea-nueva
---
# T-002 — Tarea nueva

## Objetivo
Algo.

## Criterios de aceptación
1. Algo.

## Cómo verificar
`pytest`

## Resultado
(lo completa Claude Code al terminar)
""",
    "sesiones/2026-10-05.md": "# Sesiones 2026-10-05\n\n## 10:30\nSe eligió Godot.\n",
}


def crear_memoria_v1(mem: Path) -> dict[str, bytes]:
    """Crea `mem` como repo git con la memoria v1 en un commit; devuelve {ruta relativa: bytes} de lo versionado."""
    mem.mkdir(parents=True, exist_ok=True)
    for rel, texto in ARCHIVOS.items():
        (mem / rel).parent.mkdir(parents=True, exist_ok=True)
        (mem / rel).write_text(texto, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(mem)], check=True)
    subprocess.run(["git", "-C", str(mem), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mem), "commit", "-q", "-m", "memoria v1"], check=True)
    return foto(mem)


def foto(mem: Path) -> dict[str, bytes]:
    """Contenido de todos los archivos de la memoria (sin .git ni .lock)."""
    return {p.relative_to(mem).as_posix(): p.read_bytes() for p in sorted(mem.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(mem).parts and p.name != ".lock"}
