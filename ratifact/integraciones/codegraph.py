"""codegraph (alcance proyecto): grafo de símbolos del código; señal `.codegraph/`."""
from ratifact.integraciones.base import Integracion, carpeta_existe

INTEGRACION = Integracion(
    nombre="codegraph",
    alcance="proyecto",
    detectar=carpeta_existe(".codegraph"),
    prefijo="codegraph_",
    rol="estructura del código: símbolos, llamadas y dependencias",
    limite="nunca decisiones ni estado de tareas",
    guia={
        "planificar": "si tienes herramientas `codegraph_*`, úsalas para llenar `archivos` con precisión; "
                      "si no, usa `buscar`.",
        "ejecutar": "si tienes herramientas `codegraph_*`, tras leer la spec y antes de abrir archivos llama "
                    "`codegraph_context` (o la de explorar que tengas) con el objetivo y los archivos listados; "
                    "si no, lee esos archivos.",
        "verificar": "si tienes herramientas `codegraph_*`, revisa los callers de los símbolos cambiados para "
                     "confirmar el alcance del cambio; si no, búscalos en el código.",
    },
)
