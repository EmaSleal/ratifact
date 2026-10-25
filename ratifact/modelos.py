"""Enrutamiento de modelos por rol (ADR-033 §2, ADR-035): el usuario fija qué modelo usa cada rol al delegar
(explore, write, verify). Valor global en settings.json, junto al projects.json activo (`CONFIG.parent`), con
excepciones por proyecto en su entrada de projects.json (`"models"`), combinadas rol por rol.

Independiente de cualquier integración: ratifact solo transmite la petición del usuario como guía condicional; el
cliente que no permite elegir modelo para sub-agentes la ignora. Los valores son texto libre del cliente (alias como
haiku/sonnet o ids completos): no se validan contra una lista. Se lee en cada llamada, sin caché."""
from __future__ import annotations

import json
from pathlib import Path

from ratifact import config as _cfg
from ratifact.config import ErrorMemoria

ROLES = ("explore", "write", "verify")
ARCHIVO = "settings.json"
HEREDAR = "inherit"
CLAVE = "models"


def ruta_settings(config: Path | None = None) -> Path:
    return (config or _cfg.CONFIG).parent / ARCHIVO


def _validos() -> str:
    return f"Valid roles: {', '.join(ROLES)}."


def _validar(modelos, origen: str) -> dict[str, str]:
    """`{"explore": "haiku", ...}` validado: roles conocidos y valores de texto no vacíos; si no, ErrorMemoria."""
    if not isinstance(modelos, dict):
        raise ErrorMemoria(f"{origen}: `models` must be an object like {{\"explore\": \"haiku\"}}. {_validos()}")
    desconocidos = sorted(r for r in modelos if r not in ROLES)
    if desconocidos:
        raise ErrorMemoria(f"{origen}: unknown role(s) in `models`: {', '.join(desconocidos)}. {_validos()}")
    vacios = sorted(r for r, m in modelos.items() if not isinstance(m, str) or not m.strip())
    if vacios:
        raise ErrorMemoria(f"{origen}: empty model for {', '.join(vacios)}. {_validos()}")
    return {r: m.strip() for r, m in modelos.items()}


def leer_settings(config: Path | None = None) -> dict:
    """Contenido de settings.json (modelos y política de delegación). Sin archivo: {}. JSON inválido o que no es un
    objeto: ErrorMemoria con un mensaje claro (nunca se modifica el archivo)."""
    ruta = ruta_settings(config)
    if not ruta.is_file():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ErrorMemoria(f"{ruta} is not valid JSON ({e}).") from e
    if not isinstance(datos, dict):
        raise ErrorMemoria(f"{ruta} must be a JSON object like {{\"models\": {{\"explore\": \"haiku\"}}}}.")
    return datos


def leer_global(config: Path | None = None) -> dict[str, str]:
    """Modelos globales de settings.json. Sin archivo o sin `models`: {}. JSON inválido o roles desconocidos:
    ErrorMemoria con un mensaje claro (nunca se modifica el archivo)."""
    datos = leer_settings(config)
    return _validar(datos[CLAVE], str(ruta_settings(config))) if CLAVE in datos else {}


def efectivos(entrada: dict, config: Path | None = None) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """({rol: (modelo, "global"|"project")}, avisos) para la entrada de un proyecto en projects.json. Un settings.json
    o una excepción del proyecto inválidos se ignoran con un aviso: nunca rompen la llamada que los consulta."""
    avisos: list[str] = []
    try:
        globales = leer_global(config)
    except ErrorMemoria as e:
        globales = {}
        avisos.append(f"{e} Global models ignored.")
    try:
        propios = _validar(entrada[CLAVE], "projects.json (project entry)") if CLAVE in entrada else {}
    except ErrorMemoria as e:
        propios = {}
        avisos.append(f"{e} Project models ignored.")
    salida = {r: (globales[r], "global") for r in ROLES if r in globales}
    salida.update({r: (propios[r], "project") for r in ROLES if r in propios})
    return salida, avisos


def bloque(entrada: dict) -> str:
    """Bloque "Model routing" de update_task(..., "in_progress"). Vacío si no hay ningún rol configurado (ni avisos):
    la respuesta queda idéntica a la de antes de esta función."""
    modelos, avisos = efectivos(entrada)
    if not modelos and not avisos:
        return ""
    lineas = ["Model routing (configured by the user):"]
    lineas += [f"- {r}: {modelos[r][0]} ({modelos[r][1]})" if r in modelos else f"- {r}: session model (not set)"
               for r in ROLES]
    if modelos:
        lineas.append("This is the user's explicit request to set the model when delegating each listed role to a "
                      "sub-agent; if your client cannot choose the model of sub-agents, ignore it. Roles without a "
                      "model inherit the session's model.")
    lineas += [f"⚠ {a}" for a in avisos]
    return "\n".join(lineas)


def describir(entrada: dict, config: Path | None = None) -> str:
    """Una línea para `ratifact doctor`: "explore=haiku (global), write=sonnet (project)" o "session default"."""
    modelos, _ = efectivos(entrada, config)
    return ", ".join(f"{r}={m} ({o})" for r, (m, o) in modelos.items()) or "session default"


def parsear(texto: str, actual) -> tuple[dict[str, str], str]:
    """"explore=haiku,write=inherit" → excepción nueva del proyecto (`inherit` quita el rol) y la descripción."""
    formato = (f"Format of `models`: role=model separated by commas (e.g. \"explore=haiku,write=sonnet\"; "
               f"\"{HEREDAR}\" removes the project's exception for that role). {_validos()}")
    nuevo = dict(actual) if isinstance(actual, dict) else {}
    pares = []
    for item in (x.strip() for x in texto.split(",")):
        if not item:
            continue
        rol, separador, modelo = item.partition("=")
        rol, modelo = rol.strip().lower(), modelo.strip()
        if not separador or not rol:
            raise ErrorMemoria(formato)
        if rol not in ROLES:
            raise ErrorMemoria(f"Unknown role '{rol}'. {_validos()}")
        if not modelo:
            raise ErrorMemoria(f"Empty model for '{rol}'. {formato}")
        if modelo.lower() == HEREDAR:
            nuevo.pop(rol, None)
        else:
            nuevo[rol] = modelo
        pares.append(f"{rol}={modelo}")
    if not pares:
        raise ErrorMemoria(f"Empty `models`. {formato}")
    return nuevo, ", ".join(pares)
