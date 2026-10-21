"""Bounded edit of ~/.codex/config.toml (T-013): only the `[mcp_servers.memoria-proyectos]` / `[mcp_servers.ratifact]`
tables and their sub-tables are rewritten; every other line of the file stays byte for byte. The result is accepted only
if parsing it gives exactly the original data with that one server replaced (tomllib, or tomli on Python 3.10); any
other layout (inline tables, dotted keys, multi-line strings) is refused with manual instructions."""
from __future__ import annotations

import copy
import json
import re

from ratifact.archivos import ErrorInstalacion
from ratifact.vocabulario import HERRAMIENTAS_V0

CLAVE, CLAVE_VIEJA = "ratifact", "memoria-proyectos"
_QUITAR = ("command", "args", "env")
_BARE = re.compile(r"[A-Za-z0-9_-]+")
_PARTE = re.compile(r"""\s*(?:([A-Za-z0-9_-]+)|"((?:[^"\\]|\\.)*)"|'([^']*)')\s*""")
_ASIGNACION = re.compile(r"""^\s*["']?(command|args|env)["']?\s*[=.]""")


def _parser():
    try:
        import tomllib
        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli
            return tomli
        except ModuleNotFoundError:
            return None


def parsear(texto: str, origen: str = "the file") -> dict:
    toml = _parser()
    if toml is None:
        raise ErrorInstalacion("cannot validate TOML on this Python (install `tomli`, a dependency of ratifact on "
                               "Python 3.10); nothing was changed.")
    try:
        return toml.loads(texto)
    except toml.TOMLDecodeError as e:
        raise ErrorInstalacion(f"{origen} is not valid TOML ({e}); fix it by hand, nothing was changed.") from None


def manual(exe: str) -> str:
    return (f"replace the `[mcp_servers.{CLAVE_VIEJA}]` server by hand with:\n"
            f"        [mcp_servers.{CLAVE}]\n        command = {json.dumps(exe)}\n        args = [\"serve\"]\n"
            f"      (delete its `.env` table; rename `[mcp_servers.{CLAVE_VIEJA}.tools.<tool>]` approval tables to "
            f"`[mcp_servers.{CLAVE}.tools.<tool>]`)")


def _clave(texto: str) -> list[str] | None:
    """Dotted key of a table header (`a."b.c".d` → [a, b.c, d]); None if it cannot be read."""
    partes, i = [], 0
    while True:
        m = _PARTE.match(texto, i)
        if not m:
            return None
        bare, basica, literal = m.groups()
        partes.append(bare if bare is not None else literal if literal is not None else json.loads(f'"{basica}"'))
        i = m.end()
        if i == len(texto):
            return partes
        if texto[i] != ".":
            return None
        i += 1


def _cabecera(linea: str) -> tuple[list[str] | None, bool] | None:
    """(key, is an array of tables) if the line is a table header; None otherwise."""
    s = linea.strip()
    if not s.startswith("["):
        return None
    doble = s.startswith("[[")
    cuerpo, comillas, i = s[2:] if doble else s[1:], None, 0
    while i < len(cuerpo):
        ch = cuerpo[i]
        if comillas:
            if ch == "\\" and comillas == '"':
                i += 1
            elif ch == comillas:
                comillas = None
        elif ch in "\"'":
            comillas = ch
        elif ch == "]":
            return _clave(cuerpo[:i]), doble
        i += 1
    return None, doble


def _formatear(partes: list[str]) -> str:
    return ".".join(p if _BARE.fullmatch(p) else json.dumps(p) for p in partes)


def _secciones(lineas: list[str]) -> list[tuple[int, int, list[str] | None, bool]]:
    """(start, end, key, array) of each table; the lines before the first header have key []."""
    cabeceras = [(i, *c) for i, l in enumerate(lineas) if (c := _cabecera(l)) is not None]
    inicios = [(0, [], False)] + cabeceras
    fines = [i for i, *_ in cabeceras] + [len(lineas)]
    return [(ini, fin, clave, doble) for (ini, clave, doble), fin in zip(inicios, fines)]


def _profundidad(linea: str) -> int:
    """Brackets opened minus closed outside strings and comments."""
    n, comillas, i = 0, None, 0
    while i < len(linea):
        ch = linea[i]
        if comillas:
            if ch == "\\" and comillas == '"':
                i += 1
            elif ch == comillas:
                comillas = None
        elif ch in "\"'":
            comillas = ch
        elif ch == "#":
            break
        elif ch in "[{":
            n += 1
        elif ch in "]}":
            n -= 1
        i += 1
    return n


def _sin_asignaciones(cuerpo: list[str]) -> list[str]:
    """The body of the main table without command/args/env (also multi-line arrays)."""
    salida, i = [], 0
    while i < len(cuerpo):
        if _ASIGNACION.match(cuerpo[i]):
            depth = _profundidad(cuerpo[i])
            while depth > 0 and i + 1 < len(cuerpo):
                i += 1
                depth += _profundidad(cuerpo[i])
        else:
            salida.append(cuerpo[i])
        i += 1
    return salida


def _herramienta(partes: list[str]) -> list[str]:
    """`tools.obtener_contexto` (v0 Spanish name) → `tools.get_context`."""
    if len(partes) >= 2 and partes[0] == "tools":
        return ["tools", HERRAMIENTAS_V0.get(partes[1], partes[1]), *partes[2:]]
    return partes


def esperado(datos: dict, exe: str) -> dict:
    """What the parsed file must be after the edit."""
    d = copy.deepcopy(datos)
    servidores = d.setdefault("mcp_servers", {})
    viejo, actual = servidores.pop(CLAVE_VIEJA, None), servidores.pop(CLAVE, None)
    fuente = actual if actual is not None else (viejo or {})
    nuevo = {"command": exe, "args": ["serve"], **{k: v for k, v in fuente.items() if k not in _QUITAR}}
    if isinstance(nuevo.get("tools"), dict):
        herramientas: dict = {}
        for k, v in nuevo["tools"].items():
            herramientas.setdefault(HERRAMIENTAS_V0.get(k, k), v)
        nuevo["tools"] = herramientas
    servidores[CLAVE] = nuevo
    return d


def editar(texto: str, exe: str) -> str:
    """New text of config.toml with the `ratifact` server (and without `memoria-proyectos`). ErrorInstalacion if the
    layout is not the known one or the result would not be exactly the expected data."""
    datos = parsear(texto)
    lineas = texto.splitlines(keepends=True)
    if lineas and not lineas[-1].endswith("\n"):
        lineas[-1] += "\n"
    secciones = _secciones(lineas)
    nuestras = [s for s in secciones if s[2] and s[2][:1] == ["mcp_servers"] and s[2][1:2] in ([CLAVE], [CLAVE_VIEJA])]
    if any(s[2] is None for s in secciones) or any(s[3] for s in nuestras):
        raise ErrorInstalacion("config.toml has a table header this edit does not understand; " + manual(exe))
    if any('"""' in l or "'''" in l for ini, fin, *_ in nuestras for l in lineas[ini:fin]):
        raise ErrorInstalacion("config.toml uses multi-line strings in the server table; " + manual(exe))
    clave_fuente = CLAVE if any(s[2][1] == CLAVE for s in nuestras) else CLAVE_VIEJA
    principal = [f"[mcp_servers.{CLAVE}]\n", f"command = {json.dumps(exe)}\n", 'args = ["serve"]\n']
    subtablas, vistas = [], set()
    for ini, fin, clave, _ in nuestras:
        if clave[1] != clave_fuente:
            continue
        if len(clave) == 2:
            principal += _sin_asignaciones(lineas[ini + 1:fin])
        elif clave[2] != "env":
            nueva = ["mcp_servers", CLAVE, *_herramienta(clave[2:])]
            if tuple(nueva) not in vistas:
                vistas.add(tuple(nueva))
                subtablas += [f"[{_formatear(nueva)}]\n", *lineas[ini + 1:fin]]
    bloque = principal + subtablas
    inicios = {s[0] for s in nuestras}
    salida, puesto = [], False
    for ini, fin, *_ in secciones:
        if ini in inicios:
            if not puesto:
                salida += bloque
                puesto = True
            continue
        salida += lineas[ini:fin]
    if not puesto:
        if salida and salida[-1].strip():
            salida.append("\n")
        salida += bloque
    nuevo = "".join(salida)
    try:
        resultado = parsear(nuevo, "the edited config.toml")
    except ErrorInstalacion:
        resultado = None
    if resultado != esperado(datos, exe):
        raise ErrorInstalacion("the server is also defined outside its own table (inline table or dotted keys); "
                               + manual(exe))
    return nuevo
