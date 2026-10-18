"""gentle-ai (alcance proyecto): orquestador, sub-agentes y skills; señal `.atl/`."""
from ratifact.integraciones.base import Integracion, carpeta_existe

INTEGRACION = Integracion(
    nombre="gentle-ai",
    alcance="proyecto",
    detectar=carpeta_existe(".atl"),
    prefijo="sdd-",
    rol="orquestación: sub-agentes y skills para implementar",
    limite="nunca decisiones ni estado de tareas; la spec es el contrato",
    guia={
        "ejecutar": "si tienes el orquestador de gentle-ai (sub-agentes y skills `sdd-*`), puedes implementar con "
                    "ellos: la spec define el contrato y los criterios, no el método; si no, implementa directamente.",
    },
)
