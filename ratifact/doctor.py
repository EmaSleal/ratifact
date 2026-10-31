"""`ratifact doctor` (solo lectura): versión y de dónde corre (instalación fija o copia de trabajo, P-017),
configuración en uso y grafía de sus claves, estado de cada proyecto (código, memoria, esquema, ubicación por defecto
vieja/nueva, git, integraciones), log, variables MEMORIA_PROYECTOS_*, estado de cada cliente MCP (T-013) y la lista de
acciones pendientes. Código de
salida 0 si no hay nada pendiente, 1 si hay acciones. No escribe nada."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable

from ratifact import procesos as procesos_mod
from ratifact import __version__, build, delegacion, modelos, procesos, retirado, rutas
from ratifact import config as _cfg
from ratifact.config import _ruta_config
from ratifact.esquema import VERSION_ESQUEMA
from ratifact.instalar_extras import describir_rutas, planificar_enlaces
from ratifact.instalacion import (Proceso, mensaje_sugerencia, procesos_servidor, separar_procesos,
                                  sugerencias_config)
from ratifact.upgrade import describir, planificar

SUFIJOS_ENTORNO = ("CONFIG", "LOG", "BASE")


def _donde(paquete: Path | None, acciones: list[str]) -> list[str]:
    paquete = paquete or Path(__file__).resolve().parent
    origen = rutas.origen(paquete)
    if rutas.es_copia_de_trabajo(paquete):
        acciones.append(f"clients should run the fixed installation, not the working copy: "
                        f"`uv tool install --reinstall {paquete.parent}` and configure them with `ratifact serve` "
                        "(docs/upgrade-v1.md)")
        return [f"Running from: working copy {paquete.parent} ⚠ (changes in the working tree reach the "
                "clients immediately)"]
    return [f"Running from: fixed installation {paquete}" + (f" · installed from {origen}" if origen else "")]


def _fuente(paquete: Path | None, acciones: list[str], recibo: Path | None = None) -> list[str]:
    """ADR-037 §4 (D1): with an installation from a local folder (uv tool receipt), compare that folder's package with
    the installed one. PyPI or unknown origin: nothing to compare."""
    paquete = paquete or build.PAQUETE
    if rutas.es_copia_de_trabajo(paquete):
        return []
    fuente = build.fuente_local(paquete, recibo)
    if fuente is None:
        return ["Source: not a local folder (or unknown): no source check"]
    distinta = build.fuente_desfasada(paquete, fuente)
    if distinta is None:
        acciones.append(f"the local source {fuente} recorded by uv was not found: reinstall from where the code is now "
                        "(`uv tool install --reinstall <folder>`)")
        return [f"Source: {fuente} (NOT FOUND)"]
    if distinta:
        acciones.append(f"source newer than the installation: reinstall with `{build.comando_reinstalar(fuente)}`, "
                        "then restart the clients")
        return [f"Source: {fuente} · source newer than the installation: reinstall"]
    return [f"Source: {fuente} · same as the installation"]


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


def _osrelease() -> str:
    try:
        return Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return platform.release()


def _es_wsl() -> bool:
    return sys.platform.startswith("linux") and "microsoft" in _osrelease().lower()


def _plataforma() -> list[str]:
    """ADR-012: Windows is supported only through WSL. Informational only: it never adds a pending action."""
    if sys.platform == "win32":
        return ["⚠ Native Windows is not a supported platform: install ratifact inside WSL2, with the "
                "repositories on the WSL filesystem (not under /mnt/c). The rest of the diagnosis follows."]
    if _es_wsl():
        return ["Running inside WSL: supported; keep the repositories on the WSL filesystem"]
    return []


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
        lineas += [f"  {p.nombre}", f"    code: {codigo}"]
        if p.codigo and _es_wsl() and p.codigo.as_posix().startswith("/mnt/"):
            lineas.append("    ⚠ the repository is under /mnt/ (Windows filesystem seen from WSL): slow and with git "
                          "differences; move it to the WSL filesystem")
        lineas += [
                   f"    memory: {p.mem} · {esquema} · {p.ubicacion} · git: {p.git}",
                   f"    integrations: {', '.join(p.integraciones) or 'none detected'}",
                   f"    models: {modelos.describir(p.entrada, inst.config)} · delegation="
                   "{} ({})".format(*delegacion.efectiva(p.entrada, None, inst.config)[:2])]
        valor = p.entrada.get(delegacion.CLAVE)
        if valor is not None and valor not in delegacion.POLITICAS:
            acciones.append(f"{p.nombre}: invalid `delegation` {valor!r} in projects.json (valid: "
                            f"{', '.join(delegacion.POLITICAS)}); fix it with update_project(delegation=...)")
        if modelos.CLAVE in p.entrada:
            try:
                modelos._validar(p.entrada[modelos.CLAVE], "projects.json")
            except _cfg.ErrorMemoria as e:
                acciones.append(f"{p.nombre}: {e} Fix it with update_project(models=...)")
        if not (p.codigo and p.codigo.is_dir()):
            acciones.append(f"{p.nombre}: the code folder does not exist; fix it with update_project")
        if p.existe and not p.limpio:
            acciones.append(f"{p.nombre}: memory {p.mem}: {p.git}")
        if p.codigo and (p.mem == p.codigo or p.codigo in p.mem.parents):
            acciones.append(f"{p.nombre}: the memory is inside the code repository "
                            "(it would be committed and published with the code)")
    return lineas


def _settings(config: Path, acciones: list[str]) -> list[str]:
    """settings.json (modelos globales por rol, ADR-035): JSON inválido o roles desconocidos son un problema; nunca
    se modifica."""
    ruta = modelos.ruta_settings(config)
    if not ruta.is_file():
        return [f"Settings: {ruta} (not created; models: session default)"]
    try:
        globales = modelos.leer_global(config)
    except _cfg.ErrorMemoria as e:
        acciones.append(f"settings.json: {e} Fix it by hand (ratifact never rewrites it)")
        return [f"Settings: {ruta} (INVALID)"]
    politica = modelos.leer_settings(config).get(delegacion.CLAVE)
    if politica is not None and politica not in delegacion.POLITICAS:
        acciones.append(f"settings.json: invalid `delegation` {politica!r} (valid: {', '.join(delegacion.POLITICAS)}). "
                        "Fix it by hand (ratifact never rewrites it)")
        return [f"Settings: {ruta} (INVALID)"]
    return [f"Settings: {ruta} · global models: "
            + (", ".join(f"{r}={m}" for r, m in globales.items()) or "none")
            + f" · delegation: {politica or delegacion.DEFECTO + ' (default)'}"]


def _servidores(plan, procesos: list[Proceso], lista: list[procesos_mod.ProcesoVivo] | None = None) -> list[str]:
    """Same criterion as the servers count: only PIDs with a record. Without the process list, unchanged."""
    propios, otros = separar_procesos(procesos, plan.inst.config)
    if lista is not None:
        registrados = {p.pid for p in lista if p.registrado}
        propios = [p for p in propios if p.pid in registrados]
    return [f"Running servers with this configuration: {', '.join(str(p.pid) for p in propios) or 'none'}"
            + (f" · with other configurations (ignored): {len(otros)}" if otros else "")]


def _clientes(acciones: list[str], paquete: Path | None = None) -> list[str]:
    """configured with ratifact / old configuration / not configured / not found, per client (T-013)."""
    from ratifact import clientes as cl
    lineas = ["Clients:"]
    for c in cl.clientes():
        e = cl.estado(c)
        lineas.append(f"  {c.titulo}: {e}" + (f" ({c.archivo})" if c.encontrado else ""))
        if e == cl.VIEJA:
            acciones.append(f"{c.titulo} has the old configuration ({cl.CLAVE_VIEJA} or another command): run "
                            "`ratifact install --apply` (`ratifact install` alone shows the plan)")
        elif e.startswith("error"):
            acciones.append(f"{c.titulo}: {e}")
    return lineas + _enlaces({c.nombre for c in cl.clientes() if c.encontrado}, acciones, paquete)


def _enlaces(encontrados: set[str], acciones: list[str], paquete: Path | None) -> list[str]:
    """/run-task links of the clients found: a missing, broken or foreign one is a pending action (`ratifact install
    --apply` fixes it); a real file/folder in its place is reported. Also any leftover link of the retired alias."""
    enlaces = planificar_enlaces(Path.home(), (paquete or Path(__file__).resolve().parent) / "skills", encontrados)
    otros = [e for e in enlaces if e.accion == "replace"]
    faltan = [e for e in enlaces if e.accion == "create"]
    reales = [e for e in enlaces if e.accion == "skip"]
    if otros:
        acciones.append(f"{len(otros)} /run-task link(s) point elsewhere or are broken (e.g. {otros[0].destino} → "
                        f"{otros[0].previo}): run `ratifact install --apply`")
    if faltan:
        acciones.append(f"{len(faltan)} /run-task link(s) are missing (e.g. {faltan[0].destino}): run "
                        "`ratifact install --apply`")
    for e in reales:
        acciones.append(f"{e.destino} exists and is not a link, so /run-task is not linked there: remove it by hand "
                        "and run `ratifact install --apply`")
    for o in retirado.planificar_obsoletos(Path.home()):
        acciones.append(f"{o.describir()}: run `ratifact install --apply`" if o.accion == "remove"
                        else o.describir())
    estado = "ok" if not (otros or faltan or reales) else (
        f"{len(faltan)} missing, {len(otros)} pointing elsewhere or broken, {len(reales)} blocked by a real file/folder")
    return ([f"/run-task links: {estado}"] if enlaces else []) + describir_rutas(Path.home(), encontrados)


def _servidores_vivos(procesos: Callable[[], list[Proceso]]) -> list[Proceso]:
    """The cmdline-based listing, which can fail where there is no /proc nor `ps` (native Windows): then, none."""
    try:
        return procesos()
    except (OSError, subprocess.SubprocessError):
        return []


def informe(procesos: Callable[[], list[Proceso]] = procesos_servidor, paquete: Path | None = None,
            log_viejo: Path | None = None, vivos: Callable[[], list[procesos.ProcesoVivo]] | None = None,
            recibo: Path | None = None) -> tuple[list[str], list[str]]:
    """(líneas del informe, acciones pendientes)."""
    acciones: list[str] = []
    lista, error = _listar(paquete or build.PAQUETE, vivos)
    lineas = [f"ratifact {__version__} (memory schema v{VERSION_ESQUEMA}) · build "
              f"{build.build_de(paquete or build.PAQUETE)}", *_plataforma(), *_donde(paquete, acciones),
              *_fuente(paquete, acciones, recibo), *_vivos(paquete, lista, error), *_config(acciones)]
    try:
        plan = planificar(procesos=lambda: [], log_viejo=log_viejo)
    except _cfg.ErrorMemoria as e:
        sugerencia = mensaje_sugerencia(sugerencias_config(_servidores_vivos(procesos), rutas.origen(paquete)))
        acciones.append(str(e) + (f" Hint: {sugerencia}." if sugerencia else ""))
        return (lineas + _settings(_ruta_config(), acciones) + _log(log_viejo) + _entorno(acciones)
                + _clientes(acciones, paquete), acciones)
    lineas += (_settings(plan.inst.config, acciones) + _proyectos(plan, acciones) + _log(log_viejo) + _entorno(acciones) + _servidores(plan, _servidores_vivos(procesos), lista)
               + _clientes(acciones, paquete))
    if not plan.vacio:
        pasos = describir(plan)
        acciones.insert(0, "run `ratifact upgrade` to review the plan, then `ratifact upgrade --apply` with every "
                           "client closed:\n      " + "\n      ".join(pasos))
    return lineas, acciones


def main(procesos: Callable[[], list[Proceso]] = procesos_servidor, paquete: Path | None = None,
         log_viejo: Path | None = None, vivos: Callable[[], list[procesos.ProcesoVivo]] | None = None,
         recibo: Path | None = None) -> int:
    lineas, acciones = informe(procesos, paquete, log_viejo, vivos, recibo)
    print("\n".join(lineas))
    print("Pending actions:" + ("" if acciones else " none"))
    for a in acciones:
        print(f"  - {a}")
    return 1 if acciones else 0
