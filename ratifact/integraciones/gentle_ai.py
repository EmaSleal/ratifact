"""gentle-ai (alcance proyecto): orquestador, sub-agentes y skills; señal `.atl/`."""
from ratifact.integraciones.base import Integracion, carpeta_existe

INTEGRACION = Integracion(
    nombre="gentle-ai",
    alcance="project",
    detectar=carpeta_existe(".atl"),
    prefijo="sdd-",
    rol="orchestration: sub-agents and skills to implement",
    limite="never decisions or task status; the spec is the contract",
    guia={
        "execute": "if you have the gentle-ai orchestrator (sub-agents and `sdd-*` skills), you may implement with "
                   "them: the spec defines the contract and the criteria, not the method; otherwise implement "
                   "directly.",
    },
)
