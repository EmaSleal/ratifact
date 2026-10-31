"""T-017 review 1: the stale-link cleanup of `upgrade` only skips the blocks when it is the only pending thing; the
single Claude Code entry point of /run-task; the list of checked paths and the one warning text of install/doctor."""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import RAIZ_REPO  # noqa: F401
from test_install import casa, cliente_configurado, instalar, paquete, _enlazar  # noqa: F401  (fixtures/helpers)
from test_upgrade import arbol, correr, hogar, vieja  # noqa: F401,F811  (fixtures)


# ───────────── solo_enlaces_obsoletos (single function, criterion 15) ─────────────

def _plan(**kw):
    from ratifact import upgrade
    return upgrade.Plan(inst=None, config_nueva=Path("/x"), **kw)


def test_solo_enlaces_obsoletos_unidad():
    from ratifact import upgrade
    from ratifact.retirado import Obsoleto
    quitar, aviso = Obsoleto(Path("/a"), "remove"), Obsoleto(Path("/b"), "skip")
    assert upgrade.solo_enlaces_obsoletos(_plan()) is False                       # empty plan
    assert upgrade.solo_enlaces_obsoletos(_plan(obsoletos=[aviso])) is False       # a warning is not an action
    assert upgrade.solo_enlaces_obsoletos(_plan(obsoletos=[quitar, aviso])) is True
    otros = {"migrar": ["p"], "mover": [("p", Path("/y"))], "vistas": ["p"], "log": (Path("/v"), Path("/n")),
             "bloqueos": ["x"], "config": {}}
    for campo, valor in otros.items():
        assert upgrade.solo_enlaces_obsoletos(_plan(obsoletos=[quitar], **{campo: valor})) is False, campo


def test_upgrade_mixto_con_servidor_vivo_bloquea_y_no_borra_nada(vieja, entorno, capsys):
    from ratifact.instalacion import Proceso
    propio = _enlazar(vieja["home"] / ".claude/skills/tarea", vieja["home"] / "site-packages/ratifact/skills/tarea")
    antes = arbol(entorno["tmp"])
    codigo, salida = correr(vieja, capsys, aplicar=True,
                            procesos=lambda: [Proceso(4242, "ratifact serve", vieja["config"])])
    assert codigo == 1 and "server running: pid 4242" in salida and "Aborted" in salida
    assert propio.is_symlink() and arbol(entorno["tmp"]) == antes


def test_upgrade_solo_el_enlace_con_servidor_vivo_lo_borra_y_no_toca_nada_mas(casa, paquete, capsys):
    from ratifact import upgrade
    from ratifact.instalacion import Proceso
    propio = _enlazar(casa / ".claude/skills/tarea", paquete / "skills" / "tarea")
    config = casa / ".config/ratifact/projects.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    antes = arbol(casa)
    codigo = upgrade.main(aplicar=True, procesos=lambda: [Proceso(4242, "ratifact serve", config)],
                          log_viejo=casa / "sin-log.jsonl")
    salida = capsys.readouterr().out
    assert codigo == 0 and not propio.is_symlink() and "server running" not in salida, salida
    assert arbol(casa) == antes                                            # files: identical (only a symlink went)


# ───────────── single /run-task entry point in Claude Code (criterion 16) ─────────────

def test_install_deja_un_solo_punto_de_entrada_run_task_en_claude_code(cliente_configurado, casa, paquete, capsys):
    skills, comando = casa / ".claude/skills/run-task", casa / ".claude/commands/run-task.md"
    skills.unlink()
    antiguo = _enlazar(comando, paquete / "skills" / "run-task" / "SKILL.md")
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert f"remove stale /run-task command link: {antiguo}" in salida and f"link /run-task: {skills}" in salida
    instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert skills.is_symlink() and not comando.exists() and not comando.is_symlink()


def test_enlace_antiguo_de_comando_real_o_ajeno_se_conserva_con_aviso(cliente_configurado, casa, paquete, capsys):
    comando = casa / ".claude/commands/run-task.md"
    comando.parent.mkdir(parents=True, exist_ok=True)
    comando.write_text("mine")
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert f"{comando} is not a ratifact /run-task link: left untouched" in salida and comando.read_text() == "mine"
    comando.unlink()
    ajeno = _enlazar(comando, casa / "otro" / "run-task.md")
    instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert ajeno.is_symlink()


# ───────────── checked paths (criterion 17) and one warning text (criterion 18) ─────────────

def _esperadas(casa, paquete):
    return ["Skill link paths checked:"] + [f"  {casa / r}" for r in (
        ".claude/skills/run-task", ".codex/skills/run-task", ".agents/skills/run-task",
        ".claude/commands/tarea.md", ".claude/skills/tarea", ".pi/agent/prompts/tarea.md", ".pi/agent/skills/tarea",
        ".codex/skills/tarea", ".agents/skills/tarea", ".claude/commands/run-task.md")]


def test_install_y_doctor_listan_las_mismas_rutas(cliente_configurado, casa, paquete, capsys):
    import shutil
    shutil.rmtree(casa / ".pi")                  # detected clients: claude-code + codex
    esperadas = _esperadas(casa, paquete)
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert "Nothing to do" in salida and all(l in salida.splitlines() for l in esperadas)
    bloque = salida.splitlines()
    i = bloque.index(esperadas[0])
    assert bloque[i:i + len(esperadas)] == esperadas
    from ratifact import doctor
    doctor.main(procesos=lambda: [], paquete=paquete, log_viejo=None)
    lineas = capsys.readouterr().out.splitlines()
    i = lineas.index(esperadas[0])
    assert lineas[i:i + len(esperadas)] == esperadas


def test_commands_tarea_md_propio_se_borra_y_real_se_conserva_con_el_mismo_aviso(cliente_configurado, casa, paquete,
                                                                                 capsys):
    ruta = casa / ".claude/commands/tarea.md"
    _enlazar(ruta, paquete / "skills" / "tarea" / "SKILL.md")
    instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert not ruta.is_symlink() and not ruta.exists()
    ruta.write_text("mine")
    aviso = f"{ruta} is not a ratifact /tarea link: left untouched (remove it by hand if you no longer need it)"
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert aviso in salida
    from ratifact import doctor
    doctor.main(procesos=lambda: [], paquete=paquete, log_viejo=None)
    assert aviso in capsys.readouterr().out and ruta.read_text() == "mine"


def test_aplicar_obsoleto_no_afirma_haber_borrado_un_enlace_que_cambio(tmp_path):
    from ratifact.retirado import Obsoleto, aplicar_obsoleto
    ruta = tmp_path / "tarea"
    plan = Obsoleto(ruta, "remove", "x", "tarea")
    ruta.symlink_to(tmp_path / "otra-cosa")                                  # replaced by a foreign link after the plan
    mensaje = aplicar_obsoleto(plan)
    assert ruta.is_symlink() and "remove stale" not in mensaje
    assert f"skipped: {ruta} changed since the plan" in mensaje
