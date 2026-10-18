"""engram (alcance usuario): memoria de agente. Sin señal por proyecto: nunca se detecta, solo aporta guía."""
from ratifact.integraciones.base import Integracion

INTEGRACION = Integracion(
    nombre="engram",
    alcance="usuario",
    prefijo="mem_",
    rol="memoria de agente: aprendizajes técnicos",
    limite="nunca decisiones ni estado de tareas; ante una contradicción gana la decisión acordada",
    guia={
        "cerrar": "si tienes herramientas `mem_*` (engram), guarda ahí los aprendizajes técnicos; las decisiones "
                  "nuevas solo se proponen al usuario en memoria-proyectos; si no, omite este paso.",
    },
)
