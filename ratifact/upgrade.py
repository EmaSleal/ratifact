"""`ratifact upgrade` (ADR-029): el paso explícito, con los clientes cerrados, que la migración automática no hace.
Sin `--apply` solo muestra el plan; con `--apply`, en orden y con respaldo: (1) migra al esquema v2 las memorias v1
(misma migración de T-010, tag pre-v2); (2) mueve <base>/.memorias/<p> a <base>/.ratifact/<p> (las rutas propias nunca
se mueven); (3) escribe ~/.config/ratifact/projects.json con las claves en inglés y renombra el viejo a
projects.json.bak-v1; (4) regenera DECISIONS.md/OPEN.md; (5) copia el log viejo <repo>/logs/uso.jsonl si el nuevo no
existe. Idempotente. La ejecución y la vuelta atrás están en ratifact.upgrade_aplicar."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ratifact import retirado, rutas
from ratifact.build import RECORDATORIO
from ratifact import config as _cfg
from ratifact.config import CLAVES_CONFIG
from ratifact.esquema import VERSION_ESQUEMA, _inicializada
from ratifact.instalacion import (VIEJA, Instalacion, Proceso, Proyecto, bloqueo_tomado, inventario,
                                  mensaje_sugerencia, procesos_servidor, separar_procesos, sugerencias_config)
from ratifact.registros import _vistas_en


@dataclass
class Plan:
    inst: Instalacion
    config_nueva: Path
    migrar: list[Proyecto] = field(default_factory=list)
    mover: list[tuple[Proyecto, Path]] = field(default_factory=list)
    config: dict | None = None                       # contenido nuevo de projects.json (None: no hace falta)
    vistas: list[Proyecto] = field(default_factory=list)
    log: tuple[Path, Path] | None = None             # (viejo, nuevo)
    bloqueos: list[str] = field(default_factory=list)
    otros_servidores: list[Proceso] = field(default_factory=list)
    obsoletos: list[retirado.Obsoleto] = field(default_factory=list)   # enlaces del alias retirado (ADR-039)

    @property
    def vacio(self) -> bool:
        return not (self.migrar or self.mover or self.config is not None or self.vistas or self.log or
                    any(o.accion == "remove" for o in self.obsoletos))


def _destino(p: Proyecto, base: Path) -> Path:
    return base / ".ratifact" / p.nombre


def config_en_ingles(inst: Instalacion) -> dict:
    """projects.json con las claves en inglés (si una entrada tiene las dos grafías gana la inglesa) y la memoria de
    las que están en la ruta por defecto vieja apuntando a <base>/.ratifact/<p>. El orden de las claves se conserva."""
    salida = {}
    por_nombre = {p.nombre: p for p in inst.proyectos}
    for nombre, entrada in inst.datos.items():
        if not isinstance(entrada, dict):
            salida[nombre] = entrada
            continue
        nueva: dict = {}
        for clave, valor in entrada.items():
            en = CLAVES_CONFIG.get(clave, clave)
            if en != clave and en in entrada:
                continue
            nueva[en] = valor
        p = por_nombre.get(nombre)
        if p and p.ubicacion == VIEJA:
            nueva["memory"] = str(_destino(p, inst.base))
        salida[nombre] = nueva
    return salida


def _vistas_desactualizadas(mem: Path) -> bool:
    return any(not r.is_file() or r.read_text(encoding="utf-8") != t for r, t in _vistas_en(mem).items())


def planificar(config: Path | None = None, base: Path | None = None,
               procesos: Callable[[], list[Proceso]] = procesos_servidor, log_viejo: Path | None = None) -> Plan:
    """Calcula qué haría --apply y qué lo impediría, sin escribir nada."""
    inst = inventario(config, base)
    plan = Plan(inst, rutas.config_nueva())
    for p in inst.proyectos:
        if p.error:
            plan.bloqueos.append(f"{p.nombre}: {p.error}")
        elif p.version is not None and p.version > VERSION_ESQUEMA:
            plan.bloqueos.append(f"{p.nombre}: memory schema v{p.version} is newer than this ratifact "
                                 f"(v{VERSION_ESQUEMA}); update ratifact first.")
        elif p.version is not None and p.version < VERSION_ESQUEMA:
            plan.migrar.append(p)
        elif p.version == VERSION_ESQUEMA and _vistas_desactualizadas(p.mem):
            plan.vistas.append(p)
        if p.ubicacion == VIEJA and p.existe:
            plan.mover.append((p, _destino(p, inst.base)))
            if _destino(p, inst.base).exists():
                plan.bloqueos.append(f"{p.nombre}: {_destino(p, inst.base)} already exists; move it aside by hand.")
    nueva = config_en_ingles(inst)
    if nueva != inst.datos or inst.config.resolve() != plan.config_nueva.resolve():
        plan.config = nueva
        if plan.config_nueva.exists() and inst.config.resolve() != plan.config_nueva.resolve():
            plan.bloqueos.append(f"{plan.config_nueva} already exists but the configuration in use is {inst.config} "
                                 "(set by RATIFACT_CONFIG / MEMORIA_PROYECTOS_CONFIG); merge them by hand.")
    viejo, nuevo = log_viejo or rutas.log_viejo(), rutas.log_por_defecto()
    if viejo and viejo.is_file() and not nuevo.exists() and viejo.resolve() != nuevo.resolve():
        plan.log = (viejo, nuevo)
    plan.obsoletos = retirado.planificar_obsoletos(Path.home())
    if not plan.vacio and not solo_enlaces_obsoletos(plan):
        _bloqueos(plan, procesos())
    return plan


def solo_enlaces_obsoletos(plan: Plan) -> bool:
    """True iff the only pending thing is removing stale skill links: no memory, config or log step and no block
    already found. Only then `upgrade` does not need the clients closed (it touches no memory)."""
    return (any(o.accion == "remove" for o in plan.obsoletos) and not plan.bloqueos and
            not (plan.migrar or plan.mover or plan.config is not None or plan.vistas or plan.log))


def _bloqueos(plan: Plan, procesos: list[Proceso]) -> None:
    """(a) servidores en marcha con esta configuración y .lock tomados; (b) memorias con cambios sin commit."""
    propios, plan.otros_servidores = separar_procesos(procesos, plan.inst.config)
    for pr in propios:
        plan.bloqueos.append(f"server running: pid {pr.pid} ({pr.comando[:120]}); close every client first.")
    for p in plan.inst.proyectos:
        if p.existe and bloqueo_tomado(p.mem):
            plan.bloqueos.append(f"{p.nombre}: {p.mem / '.lock'} is held by another process; close every client "
                                 "first.")
        if p.existe and _inicializada(p.mem) and not p.limpio:
            plan.bloqueos.append(f"{p.nombre}: memory {p.mem}: {p.git}; commit or discard first.")


def describir(plan: Plan) -> list[str]:
    """Líneas del plan, en el orden en que --apply lo ejecuta."""
    lineas = []
    for p in plan.migrar:
        lineas.append(f"1. migrate {p.nombre} ({p.mem}) from schema v{p.version} to v{VERSION_ESQUEMA} "
                      "(backup tag pre-v2)")
    for p, destino in plan.mover:
        lineas.append(f"2. move {p.nombre}: {p.mem} → {destino}")
    for p in plan.inst.proyectos:
        if p.ubicacion != VIEJA and p.existe and plan.config is not None:
            lineas.append(f"2. keep {p.nombre} at {p.mem} ({p.ubicacion})")
    if plan.config is not None:
        lineas.append(f"3. write {plan.config_nueva} with English keys; rename {plan.inst.config} to "
                      f"{rutas.respaldo(plan.inst.config).name}" if plan.inst.config.resolve() !=
                      plan.config_nueva.resolve() else
                      f"3. rewrite {plan.config_nueva} with English keys (copy kept as "
                      f"{rutas.respaldo(plan.config_nueva).name})")
    for p in plan.vistas:
        lineas.append(f"4. regenerate DECISIONS.md/OPEN.md of {p.nombre}")
    if plan.log:
        lineas.append(f"5. copy the usage log {plan.log[0]} → {plan.log[1]}")
    lineas += [f"6. {o.describir()}" for o in plan.obsoletos if o.accion == "remove"]
    lineas += [f"Note: {o.describir()}" for o in plan.obsoletos if o.accion == "skip"]
    return lineas


def main(aplicar: bool = False, procesos: Callable[[], list[Proceso]] = procesos_servidor,
         log_viejo: Path | None = None, origen: Path | None = None) -> int:
    from ratifact.upgrade_aplicar import ErrorUpgrade, ejecutar
    try:
        plan = planificar(procesos=procesos, log_viejo=log_viejo)
    except _cfg.ErrorMemoria as e:
        print(f"ratifact upgrade: {e}")
        sugerencia = mensaje_sugerencia(sugerencias_config(procesos(), origen or rutas.origen()))
        if sugerencia:
            print(f"Hint: {sugerencia}.")
        return 1
    print(f"Configuration: {plan.inst.config}")
    configs = sorted({str(p.config) for p in plan.otros_servidores})
    if configs:
        n = len(plan.otros_servidores)
        print(f"Ignored: {n} server process{'es' if n != 1 else ''} using another configuration "
              f"({', '.join(configs)}; pids {', '.join(str(p.pid) for p in plan.otros_servidores)})")
    if plan.vacio:
        for o in plan.obsoletos:
            print(f"Note: {o.describir()}")
        print("Nothing to do: everything is already upgraded.")
        return 0
    abortado = aplicar and bool(plan.bloqueos)
    print("Aborted — nothing was changed:" if abortado else "Applying:" if aplicar else "Plan:")
    for linea in describir(plan):
        print(f"  {linea}")
    if plan.bloqueos:
        print("Reasons:" if aplicar else "--apply would abort:")
        for b in plan.bloqueos:
            print(f"  - {b}")
        return 1
    if not aplicar:
        print("Dry run: nothing was changed. Close every client and run `ratifact upgrade --apply`.")
        return 0
    try:
        resumen = ejecutar(plan)
    except ErrorUpgrade as e:
        print(f"Upgrade failed: {e}")
        return 1
    print("Done:")
    for linea in resumen:
        print(f"  {linea}")
    print(RECORDATORIO)
    return 0
