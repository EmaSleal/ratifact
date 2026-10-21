"""`ratifact doctor` (solo lectura): versión y de dónde corre (instalación fija o copia de trabajo, P-017),
configuración en uso y grafía de sus claves, estado de cada proyecto (código, memoria, esquema, ubicación por defecto
vieja/nueva, git, integraciones), log, variables MEMORIA_PROYECTOS_* y la lista de acciones pendientes. Código de
salida 0 si no hay nada pendiente, 1 si hay acciones. No escribe nada."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from ratifact import __version__, rutas
from ratifact.config import ErrorMemoria, _ruta_config
from ratifact.esquema import VERSION_ESQUEMA
from ratifact.instalacion import Proceso, procesos_servidor, separar_procesos
from ratifact.upgrade import describir, planificar

SUFIJOS_ENTORNO = ("CONFIG", "LOG", "BASE")


def _donde(paquete: Path | None, acciones: list[str]) -> list[str]:
    paquete = paquete or Path(__file__).resolve().parent
    origen = rutas.origen(paquete)
    if rutas.es_copia_de_trabajo(paquete):
        acciones.append(f"clients should run the fixed installation, not the working copy (P-017): "
                        f"`uv tool install --reinstall {paquete.parent}` and configure them with `ratifact serve` "
                        "(docs/upgrade-v1.md)")
        return [f"Running from: working copy {paquete.parent} ⚠ (P-017: changes in the working tree reach the "
                "clients immediately)"]
    return [f"Running from: fixed installation {paquete}" + (f" · installed from {origen}" if origen else "")]


def _config(acciones: list[str]) -> list[str]:
    config = _ruta_config()
    if os.environ.get("RATIFACT_CONFIG"):
        fuente = "RATIFACT_CONFIG"
    elif os.environ.get("MEMORIA_PROYECTOS_CONFIG"):
        fuente = "MEMORIA_PROYECTOS_CONFIG (deprecated)"
    else:
        fuente = "default"
    explicita = os.environ.get("RATIFACT_CONFIG") or os.environ.get("MEMORIA_PROYECTOS_CONFIG")
    if explicita and Path(explicita).expanduser() != config:
        acciones.append(f"the CONFIG variable points to {explicita}, which `ratifact upgrade` renamed; remove it from "
                        "the client configuration")
    return [f"Configuration: {config} (from {fuente})"]


def _entorno(acciones: list[str]) -> list[str]:
    viejas = [f"MEMORIA_PROYECTOS_{s}" for s in SUFIJOS_ENTORNO if os.environ.get(f"MEMORIA_PROYECTOS_{s}")]
    for v in viejas:
        acciones.append(f"{v} is deprecated (removed in 1.1): rename it to RATIFACT_{v.rsplit('_', 1)[1]}")
    return [f"Deprecated variables: {', '.join(viejas)}" if viejas else "Deprecated variables: none"]


def _log(viejo: Path | None) -> list[str]:
    log = Path(os.environ.get("RATIFACT_LOG") or os.environ.get("MEMORIA_PROYECTOS_LOG") or rutas.log_por_defecto())
    viejo = viejo or rutas.log_viejo()
    lineas = [f"Usage log: {log} ({'exists' if log.is_file() else 'not created yet'})"]
    if viejo and viejo.is_file():
        lineas.append(f"Old usage log: {viejo} (copied by `ratifact upgrade` when the new one does not exist)")
    return lineas


def _proyectos(plan, acciones: list[str]) -> list[str]:
    inst = plan.inst
    lineas = [f"Projects folder: {inst.base}", f"Keys in projects.json: {inst.claves}", "Projects:"]
    for p in inst.proyectos:
        codigo = f"{p.codigo} ({'ok' if p.codigo and p.codigo.is_dir() else 'MISSING'})"
        if p.error:
            esquema = f"schema error: {p.error}"
        elif p.version is None:
            esquema = "not initialized" if p.existe else "missing"
        else:
            esquema = f"schema v{p.version}"
        lineas += [f"  {p.nombre}", f"    code: {codigo}",
                   f"    memory: {p.mem} · {esquema} · {p.ubicacion} · git: {p.git}",
                   f"    integrations: {', '.join(p.integraciones) or 'none detected'}"]
        if not (p.codigo and p.codigo.is_dir()):
            acciones.append(f"{p.nombre}: the code folder does not exist; fix it with update_project")
        if p.existe and not p.limpio:
            acciones.append(f"{p.nombre}: memory {p.mem}: {p.git}")
        if p.codigo and (p.mem == p.codigo or p.codigo in p.mem.parents):
            acciones.append(f"{p.nombre}: the memory is inside the code repository (ADR-010)")
    return lineas


def _servidores(plan, procesos: list[Proceso]) -> list[str]:
    propios, otros = separar_procesos(procesos, plan.inst.config)
    return [f"Running servers with this configuration: {', '.join(str(p.pid) for p in propios) or 'none'}"
            + (f" · with other configurations (ignored): {len(otros)}" if otros else "")]


def informe(procesos: Callable[[], list[Proceso]] = procesos_servidor, paquete: Path | None = None,
            log_viejo: Path | None = None) -> tuple[list[str], list[str]]:
    """(líneas del informe, acciones pendientes)."""
    acciones: list[str] = []
    lineas = [f"ratifact {__version__} (memory schema v{VERSION_ESQUEMA})", *_donde(paquete, acciones),
              *_config(acciones)]
    try:
        plan = planificar(procesos=lambda: [], log_viejo=log_viejo)
    except ErrorMemoria as e:
        acciones.append(str(e))
        return lineas + _log(log_viejo) + _entorno(acciones), acciones
    lineas += _proyectos(plan, acciones) + _log(log_viejo) + _entorno(acciones) + _servidores(plan, procesos())
    if not plan.vacio:
        pasos = describir(plan)
        acciones.insert(0, "run `ratifact upgrade` to review the plan, then `ratifact upgrade --apply` with every "
                           "client closed:\n      " + "\n      ".join(pasos))
    return lineas, acciones


def main(procesos: Callable[[], list[Proceso]] = procesos_servidor, paquete: Path | None = None,
         log_viejo: Path | None = None) -> int:
    lineas, acciones = informe(procesos, paquete, log_viejo)
    print("\n".join(lineas))
    print("Pending actions:" + ("" if acciones else " none"))
    for a in acciones:
        print(f"  - {a}")
    return 1 if acciones else 0
