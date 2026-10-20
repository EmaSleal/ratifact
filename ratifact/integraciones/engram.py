"""engram (alcance usuario): memoria de agente. Sin señal por proyecto: nunca se detecta, solo aporta guía."""
from ratifact.integraciones.base import Integracion

INTEGRACION = Integracion(
    nombre="engram",
    alcance="user",
    prefijo="mem_",
    rol="agent memory: technical learnings",
    limite="never decisions or task status; on a contradiction the accepted decision wins",
    guia={
        "close": "if you have `mem_*` tools (engram), save technical learnings there; new decisions are only "
                 "proposed to the user in memoria-proyectos; otherwise skip this step.",
    },
)
