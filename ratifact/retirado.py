"""The /tarea alias was retired in 1.0.0 (ADR-039). Older `ratifact install` runs linked it into the clients; this module
finds those links and removes them, but ONLY a symlink that points to a ratifact package or checkout (its `skills/tarea`
folder or `skills/tarea/SKILL.md`). A real file or folder, or a link to anything else, is reported and never touched.
Planning only reads; applying removes the link itself, never its target."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

NOMBRE = "tarea"


@dataclass
class Obsoleto:
    ruta: Path
    accion: str                  # remove | skip
    previo: str = ""             # raw link target ("" for a real file/folder)

    def describir(self) -> str:
        if self.accion == "remove":
            return f"remove stale /{NOMBRE} link: {self.ruta}"
        return (f"{self.ruta} is not a ratifact /{NOMBRE} link: left untouched (remove it by hand if you no longer "
                "need it)")


def rutas_candidatas(home: Path) -> list[Path]:
    """Every place an old install could have linked the alias, whichever clients are detected now."""
    return [home / ".claude" / "commands" / f"{NOMBRE}.md", home / ".claude" / "skills" / NOMBRE,
            home / ".pi" / "agent" / "prompts" / f"{NOMBRE}.md", home / ".pi" / "agent" / "skills" / NOMBRE,
            home / ".codex" / "skills" / NOMBRE, home / ".agents" / "skills" / NOMBRE]


def _es_de_ratifact(base: Path) -> bool:
    if base.name == "ratifact" and ((base / "__init__.py").is_file() or base.parent.name == "site-packages"):
        return True                  # site-packages: a reinstall into another Python leaves broken links
    if (base / "ratifact" / "__init__.py").is_file():
        return True
    try:
        return any(l.replace(" ", "") == 'name="ratifact"'
                   for l in (base / "pyproject.toml").read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def es_enlace_propio(ruta: Path) -> bool:
    """A symlink whose target (resolved lexically; it may be broken) is <ratifact package or checkout>/skills/tarea."""
    if not ruta.is_symlink():
        return False
    destino = Path(os.path.normpath(os.path.join(ruta.parent, os.readlink(ruta))))
    if destino.name == "SKILL.md":
        destino = destino.parent
    return destino.name == NOMBRE and destino.parent.name == "skills" and _es_de_ratifact(destino.parent.parent)


def planificar_obsoletos(home: Path) -> list[Obsoleto]:
    salida = []
    for ruta in rutas_candidatas(home):
        if ruta.is_symlink():
            previo = os.readlink(ruta)
            salida.append(Obsoleto(ruta, "remove" if es_enlace_propio(ruta) else "skip", previo))
        elif ruta.exists():
            salida.append(Obsoleto(ruta, "skip"))
    return salida


def aplicar_obsoleto(o: Obsoleto) -> str:
    if o.accion != "remove" or not es_enlace_propio(o.ruta):      # re-checked: it may have changed since the plan
        return o.describir()
    os.unlink(o.ruta)
    return o.describir()
