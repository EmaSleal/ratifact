"""Running-process sections of `ratifact doctor` (read only): `ratifact serve` servers and their listing."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from ratifact import build, procesos
from ratifact.instalacion import Proceso, separar_procesos


def _listar(paquete: Path, vivos: Callable[[], list[procesos.ProcesoVivo]] | None):
    """(process list, error text): the list is None when it cannot be obtained (platform without `ps`, etc.)."""
    try:
        return (vivos() if vivos else procesos.procesos_vivos(paquete)), ""
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)


def _vivos(paquete: Path | None, lista: list[procesos.ProcesoVivo] | None, error: str = "") -> list[str]:
    """ADR-037 §5 and ADR-038: servers are the `ratifact serve` processes with a PID record; a wrapper (Claude Desktop
    on Linux) is shown inside its server's entry; one without a record is listed apart and not counted. Read only."""
    paquete = paquete or build.PAQUETE
    if lista is None:
        return [f"Running `ratifact serve` processes: cannot be listed ({error})"]
    ins = procesos.modificacion_instalacion(paquete)
    cuando = f" (installation modified {ins:%Y-%m-%d %H:%M:%S})" if ins else ""
    servidores = [p for p in lista if p.registrado]
    sin_registro = [p for p in lista if not p.registrado and not p.es_envoltorio]
    if not servidores and not sin_registro:
        return [f"Running `ratifact serve` processes: none{cuando}"]
    lineas = [f"Running `ratifact serve` servers: {len(servidores)}{cuando}" + (":" if servidores else "")]
    for p in servidores:
        marca = {procesos.ANTERIOR: f" ⚠ started BEFORE the installation and runs different content (ratifact {p.build}): "
                                 "restart its client",
                 procesos.MISMO: f" · started before the reinstallation, same content (ratifact {p.build}): nothing to do"
                 }.get(p.estado, "")
        envoltorio = f" (wrapper {p.envoltorio.pid}, {p.envoltorio.padre})" if p.envoltorio else ""
        lineas.append(f"  PID {p.pid} · started {p.inicio:%Y-%m-%d %H:%M:%S} · parent {p.padre}{envoltorio}{marca}")
    if sin_registro:
        lineas.append("Unregistered processes (possible server from before PID records, or wrapper); "
                      "not counted as servers:")
        for p in sin_registro:
            lineas.append(f"  PID {p.pid} · started {p.inicio:%Y-%m-%d %H:%M:%S} · parent {p.padre}")
    return lineas


def _servidores(plan, lista_cmd: list[Proceso], lista: list[procesos.ProcesoVivo] | None = None) -> list[str]:
    """Same criterion as the servers count: only PIDs with a record. Without the process list, unchanged."""
    propios, otros = separar_procesos(lista_cmd, plan.inst.config)
    if lista is not None:
        registrados = {p.pid for p in lista if p.registrado}
        propios = [p for p in propios if p.pid in registrados]
    return [f"Running servers with this configuration: {', '.join(str(p.pid) for p in propios) or 'none'}"
            + (f" · with other configurations (ignored): {len(otros)}" if otros else "")]


def _servidores_vivos(listar: Callable[[], list[Proceso]]) -> list[Proceso]:
    """The cmdline-based listing, which can fail where there is no /proc nor `ps` (native Windows): then, none."""
    try:
        return listar()
    except (OSError, subprocess.SubprocessError):
        return []
