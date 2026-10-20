"""codegraph (alcance proyecto): grafo de símbolos del código; señal `.codegraph/`."""
from ratifact.integraciones.base import Integracion, carpeta_existe

INTEGRACION = Integracion(
    nombre="codegraph",
    alcance="project",
    detectar=carpeta_existe(".codegraph"),
    prefijo="codegraph_",
    rol="code structure: symbols, calls and dependencies",
    limite="never decisions or task status",
    guia={
        "plan": "if you have `codegraph_*` tools, use them to fill `files` precisely; otherwise use `search`.",
        "execute": "if you have `codegraph_*` tools, after reading the spec and before opening files call "
                   "`codegraph_context` (or the explore tool you have) with the goal and the listed files; "
                   "otherwise read those files.",
        "verify": "if you have `codegraph_*` tools, check the callers of the changed symbols to confirm the scope "
                  "of the change; otherwise search for them in the code.",
    },
)
