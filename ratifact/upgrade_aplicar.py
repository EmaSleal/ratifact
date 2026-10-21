"""Ejecución de `ratifact upgrade --apply` con vuelta atrás (ADR-029). Cada paso registra cómo deshacerse; si un paso
falla, se deshace y todo queda como estaba antes de él. Los pasos 2 (mover memorias) y 3 (projects.json) son una
unidad: la configuración vieja apunta a las rutas viejas, así que si falla el 3 las memorias movidas vuelven a su
lugar. Lo hecho por los pasos anteriores que ya terminaron (migraciones con su tag, o 2+3) se conserva."""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from ratifact import esquema, rutas
from ratifact.esquema import VERSION_ESQUEMA
from ratifact.registros import _escribir_atomico, _vistas_en
from ratifact.upgrade import Plan
from ratifact.vocabulario import VISTA_ABIERTOS, VISTA_DECISIONES


class ErrorUpgrade(Exception):
    pass


def _git(mem: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(mem), *args], capture_output=True, text=True)


@contextmanager
def _bloqueo(mem: Path):
    """El .lock de la memoria, sin espera: si un servidor arrancó después del chequeo, el paso falla."""
    with open(mem / ".lock", "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ErrorUpgrade(f"{mem / '.lock'} is held by another process (a server started?)") from None
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _respaldo_libre(config: Path) -> Path:
    """projects.json.bak-v1 (o -2, -3… si ya existe uno: un respaldo nunca se pisa ni se borra)."""
    destino, n = rutas.respaldo(config), 1
    while destino.exists():
        n += 1
        destino = config.with_name(f"{rutas.respaldo(config).name}-{n}")
    return destino


def _escribir_config(destino: Path, datos: dict) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(destino, json.dumps(datos, indent=2, ensure_ascii=False) + "\n")


# ───────────────────────── pasos ─────────────────────────
# Cada paso devuelve sus líneas del resumen y agrega a `deshacer` las acciones que lo revierten.

def _paso_migrar(plan: Plan, deshacer: list[Callable[[], None]]) -> list[str]:
    hecho = []
    for p in plan.migrar:
        vacias = esquema._carpetas_vacias(p.mem)
        tags = set(_git(p.mem, "tag", "-l", "pre-v*").stdout.split())
        with _bloqueo(p.mem):
            aviso = esquema._migrar(p.nombre, p.mem, p.version)
        tag = (set(_git(p.mem, "tag", "-l", "pre-v*").stdout.split()) - tags).pop()
        deshacer.append(lambda mem=p.mem, tag=tag, vacias=vacias: esquema._restaurar(mem, tag, vacias))
        hecho.append(f"{p.nombre}: {aviso.strip('()')}")
    return hecho


def _paso_mover(plan: Plan, deshacer: list[Callable[[], None]]) -> list[str]:
    hecho = []
    raiz = plan.inst.base / ".ratifact"
    if not raiz.exists():
        raiz.mkdir(parents=True)
        deshacer.append(lambda: raiz.rmdir() if raiz.is_dir() and not any(raiz.iterdir()) else None)
    for p, destino in plan.mover:
        os.rename(p.mem, destino)
        deshacer.append(lambda origen=p.mem, destino=destino: os.rename(destino, origen))
        hecho.append(f"{p.nombre}: moved {p.mem} → {destino}")
    return hecho


def _paso_config(plan: Plan, deshacer: list[Callable[[], None]]) -> list[str]:
    actual, nueva = plan.inst.config, plan.config_nueva
    original = actual.read_bytes()
    bak = _respaldo_libre(actual)
    if actual.resolve() == nueva.resolve():
        shutil.copy2(actual, bak)
        deshacer.append(lambda: (actual.write_bytes(original), bak.unlink()))
        _escribir_config(nueva, plan.config)
        return [f"rewrote {nueva} with English keys (previous version: {bak})"]
    deshacer.append(lambda: nueva.unlink(missing_ok=True))
    _escribir_config(nueva, plan.config)
    os.rename(actual, bak)
    deshacer.append(lambda: os.rename(bak, actual))
    return [f"wrote {nueva} with English keys", f"renamed {actual} → {bak} (kept, never deleted)"]


def _memorias_finales(plan: Plan) -> list[tuple[str, Path]]:
    movidas = {p.nombre: destino for p, destino in plan.mover}
    return [(p.nombre, movidas.get(p.nombre, p.mem)) for p in plan.inst.proyectos]


def _paso_vistas(plan: Plan, deshacer: list[Callable[[], None]]) -> list[str]:
    hecho = []
    for nombre, mem in _memorias_finales(plan):
        if not mem.is_dir() or not esquema._inicializada(mem) or esquema._version_esquema(mem) != VERSION_ESQUEMA:
            continue
        vistas = _vistas_en(mem)
        if all(r.is_file() and r.read_text(encoding="utf-8") == t for r, t in vistas.items()):
            continue
        cabeza = _git(mem, "rev-parse", "HEAD").stdout.strip()
        deshacer.append(lambda mem=mem, cabeza=cabeza: _git(mem, "reset", "-q", "--hard", cabeza))
        with _bloqueo(mem):
            for ruta, texto in vistas.items():
                _escribir_atomico(ruta, texto)
            archivos = [VISTA_DECISIONES, VISTA_ABIERTOS]
            mensaje = "memoria: regenerate views (ratifact upgrade)"
            for paso in (["add", "--", *archivos], ["commit", "-q", "-m", mensaje, "--", *archivos]):
                r = _git(mem, *paso)
                if r.returncode != 0:
                    raise ErrorUpgrade(f"git {paso[0]} failed in {mem}: {(r.stdout + r.stderr).strip()[:200]}")
        sha = _git(mem, "rev-parse", "--short", "HEAD").stdout.strip()
        hecho.append(f"{nombre}: regenerated DECISIONS.md/OPEN.md · commit {sha}")
    return hecho


def _paso_log(plan: Plan, deshacer: list[Callable[[], None]]) -> list[str]:
    viejo, nuevo = plan.log
    nuevo.parent.mkdir(parents=True, exist_ok=True)
    tmp = nuevo.with_name(nuevo.name + ".tmp")
    deshacer.append(lambda: (tmp.unlink(missing_ok=True), nuevo.unlink(missing_ok=True)))
    shutil.copy2(viejo, tmp)
    os.replace(tmp, nuevo)
    return [f"copied the usage log {viejo} → {nuevo} (the old one is kept)"]


PASOS = (("1", "migrate memories to schema v2", _paso_migrar, lambda plan: plan.migrar),
         ("2", "move memories to .ratifact/", _paso_mover, lambda plan: plan.mover),
         ("3", "write projects.json with English keys", _paso_config, lambda plan: plan.config is not None),
         ("4", "regenerate views", _paso_vistas, lambda plan: True),
         ("5", "copy the usage log", _paso_log, lambda plan: plan.log))


def ejecutar(plan: Plan) -> list[str]:
    """Aplica el plan en orden. Si un paso falla, ejecuta su vuelta atrás (y la del paso 2 si falló el 3) y lanza
    ErrorUpgrade con lo que quedó hecho y lo que se revirtió."""
    hechos: dict[str, list[str]] = {}
    deshacer_por_paso: dict[str, list[Callable[[], None]]] = {}
    for numero, nombre, paso, aplica in PASOS:
        if not aplica(plan):
            continue
        deshacer: list[Callable[[], None]] = []
        try:
            hechos[numero] = paso(plan, deshacer)
        except Exception as e:
            revertir = ["2", numero] if numero == "3" and "2" in hechos else [numero]
            deshacer_por_paso[numero] = deshacer
            fallos = []
            for n in reversed(revertir):
                for accion in reversed(deshacer_por_paso.get(n, [])):
                    try:
                        accion()
                    except Exception as f:     # se sigue deshaciendo lo demás; se informa
                        fallos.append(f"{type(f).__name__}: {f}")
            quedan = [l for n, lineas in hechos.items() if n not in revertir for l in lineas]
            raise ErrorUpgrade(
                f"step {numero} ({nombre}) failed: {type(e).__name__}: {e}. Reverted: "
                + " and ".join(f"step {n}" + (" (memories moved back)" if n == "2" else "") for n in revertir) + "."
                + (f" Kept from earlier steps: {'; '.join(quedan)}." if quedan else " Nothing else was changed.")
                + (f" Could not revert everything ({'; '.join(fallos)}): check by hand." if fallos else "")) from e
        deshacer_por_paso[numero] = deshacer
    return [l for lineas in hechos.values() for l in lineas] or ["nothing changed"]
