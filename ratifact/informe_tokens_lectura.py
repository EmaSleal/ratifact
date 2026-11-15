"""Transcript reader of the token usage section: metadata only, never message content. Tolerant: unreadable or odd
lines and files are skipped. Per session it keeps the instants of ALL its lines (main file plus its subagent files:
a subagent's activity counts as the session's activity) so the attribution can ask "is there a line near t?"."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path

CAMPOS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


@dataclass
class Mensaje:
    ts: dt.datetime
    rama: str | None
    modelo: str
    trabajador: bool
    agente: str | None
    cifras: list[int]


@dataclass
class Sesion:
    cwds: set = field(default_factory=set)
    instantes: list = field(default_factory=list)     # every line with a timestamp, sorted once loaded
    por_rama: dict = field(default_factory=dict)      # gitBranch -> sorted instants of the lines on that branch
    mensajes: dict = field(default_factory=dict)


def directorio_base() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base).expanduser() if base else Path.home() / ".claude") / "projects"


def _instante(texto) -> dt.datetime | None:
    if not isinstance(texto, str):
        return None
    texto = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), texto)
    texto = texto[:-1] + "+00:00" if texto.endswith("Z") else texto      # fromisoformat takes "Z" only from 3.11
    try:
        t = dt.datetime.fromisoformat(texto)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _texto(valor) -> str | None:
    return valor if isinstance(valor, str) and valor else None


def _linea(d: dict, clave_defecto, es_sub: bool, ruta: Path, s: Sesion) -> None:
    if _texto(d.get("cwd")):
        s.cwds.add(d["cwd"])
    ts = _instante(d.get("timestamp"))
    if ts is not None:
        s.instantes.append(ts)
        if _texto(d.get("gitBranch")):
            s.por_rama.setdefault(d["gitBranch"], []).append(ts)
    msg = d.get("message")
    uso = msg.get("usage") if isinstance(msg, dict) else None
    if not isinstance(uso, dict):
        return
    cifras = [uso[c] if type(uso.get(c)) is int and uso[c] >= 0 else 0 for c in CAMPOS]
    modelo = _texto(msg.get("model")) or "unknown"
    if not any(type(uso.get(c)) is int for c in CAMPOS) or ts is None or modelo == "<synthetic>":
        return
    mid, rid = _texto(msg.get("id")), _texto(d.get("requestId"))
    clave = (mid, rid) if mid or rid else clave_defecto
    previo = s.mensajes.get(clave)
    if previo:                                   # repeated message: the maximum of each field
        previo.cifras = [max(a, b) for a, b in zip(previo.cifras, cifras)]
        return
    trabajador = es_sub or d.get("isSidechain") is True
    agente = str(ruta) if es_sub else _texto(d.get("agentId"))
    s.mensajes[clave] = Mensaje(ts, _texto(d.get("gitBranch")), modelo, trabajador, agente if trabajador else None,
                                cifras)


def cargar_sesiones(base: Path, desde: dt.datetime) -> list[Sesion]:
    """One Sesion per session (its file plus its `subagents/agent-*.jsonl`); files not modified since `desde` are
    skipped; each file is read line by line."""
    sesiones: dict[Path, Sesion] = {}
    for ruta in sorted(base.glob("**/*.jsonl")):
        try:
            if ruta.stat().st_mtime < desde.timestamp():
                continue
        except OSError:
            continue
        es_sub = ruta.parent.name == "subagents" and ruta.name.startswith("agent-")
        s = sesiones.setdefault(ruta.parent.parent if es_sub else ruta.with_suffix(""), Sesion())
        try:
            with ruta.open(encoding="utf-8", errors="replace") as f:
                for n, linea in enumerate(f):
                    try:
                        d = json.loads(linea)
                    except (ValueError, RecursionError):
                        continue
                    if isinstance(d, dict):
                        _linea(d, (str(ruta), n), es_sub, ruta, s)
        except OSError:
            continue
    for s in sesiones.values():
        s.instantes.sort()
        for v in s.por_rama.values():
            v.sort()
    return list(sesiones.values())


def hay_linea(instantes: list, a: dt.datetime, b: dt.datetime) -> bool:
    """True when the sorted list has an instant in [a, b]."""
    i = bisect_left(instantes, a)
    return i < len(instantes) and instantes[i] <= b
