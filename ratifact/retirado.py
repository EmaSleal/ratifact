"""The /tarea alias was retired in 1.0.0 (ADR-039). Older `ratifact install` runs linked it into the clients; this module
finds those links and removes them, but ONLY a symlink that points to a ratifact package or checkout (its `skills/tarea`
folder or `skills/tarea/SKILL.md`). A real file or folder, or a link to anything else, is reported and never touched.
Planning only reads; applying removes the link itself, never its target."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

NOMBRE = "tarea"


RUN_TASK = "run-task"


@dataclass
class Obsoleto:
    ruta: Path
    accion: str                  # remove | skip
    previo: str = ""             # raw link target ("" for a real file/folder)
    skill: str = NOMBRE          # tarea (retired alias) | run-task (legacy Claude Code command link)

    def describir(self) -> str:
        if self.accion == "remove":
            if self.skill == RUN_TASK:
                return f"remove stale /{RUN_TASK} command link: {self.ruta}"
            return f"remove stale /{self.skill} link: {self.ruta}"
        return (f"{self.ruta} is not a ratifact /{self.skill} link: left untouched (remove it by hand if you no "
                "longer need it)")


def candidatas(home: Path) -> list[tuple[Path, str]]:
    """(path, skill) of every place an old install could have linked something that is no longer linked: the retired
    alias in any client (whichever clients are detected now) and the old Claude Code command link of /run-task
    (the canonical Claude Code destination is now ~/.claude/skills/run-task)."""
    return [(home / ".claude" / "commands" / f"{NOMBRE}.md", NOMBRE), (home / ".claude" / "skills" / NOMBRE, NOMBRE),
            (home / ".pi" / "agent" / "prompts" / f"{NOMBRE}.md", NOMBRE),
            (home / ".pi" / "agent" / "skills" / NOMBRE, NOMBRE),
            (home / ".codex" / "skills" / NOMBRE, NOMBRE), (home / ".agents" / "skills" / NOMBRE, NOMBRE),
            (home / ".claude" / "commands" / f"{RUN_TASK}.md", RUN_TASK)]


def rutas_candidatas(home: Path) -> list[Path]:
    return [r for r, _ in candidatas(home)]


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


def es_enlace_propio(ruta: Path, skill: str = NOMBRE) -> bool:
    """A symlink whose target (resolved lexically; it may be broken) is <ratifact package or checkout>/skills/<skill>
    (the folder or its SKILL.md)."""
    if not ruta.is_symlink():
        return False
    destino = Path(os.path.normpath(os.path.join(ruta.parent, os.readlink(ruta))))
    if destino.name == "SKILL.md":
        destino = destino.parent
    return destino.name == skill and destino.parent.name == "skills" and _es_de_ratifact(destino.parent.parent)


def planificar_obsoletos(home: Path) -> list[Obsoleto]:
    salida = []
    for ruta, skill in candidatas(home):
        if ruta.is_symlink():
            previo = os.readlink(ruta)
            salida.append(Obsoleto(ruta, "remove" if es_enlace_propio(ruta, skill) else "skip", previo, skill))
        elif ruta.exists():
            salida.append(Obsoleto(ruta, "skip", "", skill))
    return salida


def aplicar_obsoleto(o: Obsoleto) -> str:
    if o.accion != "remove":
        return o.describir()
    if not es_enlace_propio(o.ruta, o.skill):             # re-checked: it may have changed since the plan
        return f"skipped: {o.ruta} changed since the plan and is no longer a ratifact /{o.skill} link; left untouched"
    os.unlink(o.ruta)
    return o.describir()
