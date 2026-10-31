"""`ratifact install` (T-013, criteria 1, 3–7): plan by default, `--apply` executes it; `--client` limits it to one
client; Claude Code permissions and the generated CLAUDE.md/AGENTS.md block move to `ratifact`; /run-task is linked
from the installed package; from scratch it creates an empty projects.json; it reports the integrations without asking
and a second apply changes nothing. Everything runs in a temporary HOME with a stub `claude`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import RAIZ_REPO, crear_repo, recargar_servidor
from test_install_clientes import ClaudeFalso
from test_upgrade import arbol

EXE = "/opt/tools/bin/ratifact"


@pytest.fixture
def casa(entorno, monkeypatch):
    """Empty HOME (+ XDG) without the MEMORIA_PROYECTOS_* variables of the common fixture."""
    home = entorno["tmp"] / "home"
    home.mkdir()
    for k, v in {"HOME": home, "XDG_STATE_HOME": home / ".local" / "state", "XDG_CONFIG_HOME": home / ".config",
                 "RATIFACT_BASE": home / "Projects"}.items():
        monkeypatch.setenv(k, str(v))
    for k in ("RATIFACT_CONFIG", "RATIFACT_LOG", "MEMORIA_PROYECTOS_CONFIG", "MEMORIA_PROYECTOS_LOG",
              "MEMORIA_PROYECTOS_BASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    (home / "Projects").mkdir()
    return home


@pytest.fixture
def paquete(tmp_path):
    """A fixed installation of the package (not the working copy), with the skills that ship in the wheel."""
    destino = tmp_path / "site-packages" / "ratifact"
    shutil.copytree(RAIZ_REPO / "ratifact" / "skills", destino / "skills")
    return destino


def instalar(capsys, paquete, aplicar=False, cliente=None, claude=None, correr=None, procesos=lambda: []):
    from ratifact import instalar as modulo
    kwargs = {"correr": correr} if correr else {}
    codigo = modulo.main(aplicar=aplicar, cliente=cliente, ejecutable=EXE, paquete=paquete, claude=claude,
                         procesos=procesos, **kwargs)
    return codigo, capsys.readouterr().out


def _json(ruta: Path, datos) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=2))
    return ruta


@pytest.fixture
def maquina(casa):
    """The four clients with the pre-T-013 configuration, a registered project with Claude Code permissions and the
    v1 block, and the old /run-task links of the working copy."""
    from ratifact.plantillas import PLANTILLA_AGENTES_V1
    viejo = {"command": "/home/u/.local/bin/ratifact", "args": ["serve"]}
    desktop = _json(casa / ".config/Claude/claude_desktop_config.json",
                    {"mcpServers": {"otro": {"command": "x"}, "memoria-proyectos": viejo}, "preferences": {"a": 1}})
    claude_json = _json(casa / ".claude.json", {"numStartups": 1, "mcpServers": {"memoria-proyectos": viejo}})
    pi = _json(casa / ".pi/agent/mcp.json", {"mcpServers": {"engram": {"command": "engram"}}})
    codex = casa / ".codex" / "config.toml"
    codex.parent.mkdir()
    codex.write_text('model = "x"\n\n[mcp_servers.memoria-proyectos]\ncommand = "uv"\nargs = ["run"]\n\n'
                     '[mcp_servers.memoria-proyectos.env]\nMEMORIA_PROYECTOS_CONFIG = "/r/projects.json"\n')
    ajustes = _json(casa / ".claude/settings.json", {"permissions": {
        "allow": ["Read", "mcp__memoria-proyectos", "mcp__codegraph__*"],
        "ask": ["mcp__memoria-proyectos__confirmar_decision", "mcp__memoria-proyectos__accept_decisions"]},
        "theme": "dark"})
    repo = crear_repo(casa / "Projects" / "demo")
    (repo / ".codegraph").mkdir()
    proyecto = _json(repo / ".claude/settings.json", {"permissions": {
        "allow": ["mcp__memoria-proyectos__get_context", "mcp__ratifact__get_context", "Bash(git status:*)"],
        "deny": ["mcp__memoria-proyectos__register_project"]}})
    bloque = PLANTILLA_AGENTES_V1.format(proyecto="demo")
    (repo / "AGENTS.md").write_text(f"# Demo\n\n{bloque}\nTest command (from the repository root): `pytest`\n")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    otro = crear_repo(casa / "Projects" / "otro")
    (otro / "AGENTS.md").write_text(bloque.replace("Before working", "Antes de trabajar"))    # edited by hand
    config = _json(casa / ".config/ratifact/projects.json", {
        "demo": {"path": str(repo), "memory": str(casa / "Projects/.ratifact/demo")},
        "otro": {"path": str(otro), "memory": str(casa / "Projects/.ratifact/otro"),
                 "integrations": {"codegraph": "off"}}})
    vieja = casa / "repo-viejo" / "skills" / "run-task"
    vieja.mkdir(parents=True)
    (casa / "repo-viejo" / "ratifact").mkdir()
    (casa / "repo-viejo" / "ratifact" / "__init__.py").write_text("")           # an old own checkout
    (casa / ".claude/commands").mkdir()
    (casa / ".claude/commands/run-task.md").symlink_to(vieja / "SKILL.md")
    (casa / ".agents/skills/tarea").mkdir(parents=True)                       # a real folder: never replaced
    return {"desktop": desktop, "claude_json": claude_json, "pi": pi, "codex": codex, "ajustes": ajustes,
            "proyecto": proyecto, "repo": repo, "otro": otro, "config": config, "home": casa}


def test_plan_por_defecto_no_cambia_nada(maquina, paquete, capsys):
    antes = arbol(maquina["home"])
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert codigo == 0 and arbol(maquina["home"]) == antes, salida
    for esperado in (f"Executable: {EXE}", "Claude Desktop: old configuration → replace `memoria-proyectos` with "
                     "`ratifact`", "Claude Code: old configuration", "via `claude mcp add --scope user`",
                     "Pi: not configured → add `ratifact`", "Codex: old configuration",
                     "mcp__memoria-proyectos__confirmar_decision → mcp__ratifact__accept_decision",
                     f"{maquina['repo'] / 'AGENTS.md'}", f"{maquina['home'] / '.codex/skills/run-task'} → "
                     f"{paquete / 'skills' / 'run-task'}", "Dry run: nothing was changed"):
        assert esperado in salida, (esperado, salida)
    bloques, manuales = salida.split("Project block in CLAUDE.md/AGENTS.md")[1].split("Manual steps")
    assert str(maquina["otro"] / "AGENTS.md") not in bloques                 # not the exact generated block…
    assert f"{maquina['otro'] / 'AGENTS.md'} mentions `memoria-proyectos`" in manuales     # …so it is listed instead


def test_apply_configura_todo_y_el_segundo_no_cambia_nada(maquina, paquete, capsys):
    falso = ClaudeFalso(maquina["claude_json"])
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=falso)
    assert codigo == 0, salida
    from ratifact import clientes
    for c in clientes.clientes(claude="/usr/bin/claude"):
        assert clientes.estado(c, EXE) == clientes.CONFIGURADO, c.nombre
    assert json.loads(maquina["desktop"].read_text())["preferences"] == {"a": 1}
    ajustes = json.loads(maquina["ajustes"].read_text())
    assert ajustes["theme"] == "dark" and ajustes["permissions"] == {
        "allow": ["Read", "mcp__ratifact", "mcp__codegraph__*"],
        "ask": ["mcp__ratifact__accept_decision", "mcp__ratifact__accept_decisions"]}
    assert json.loads(maquina["proyecto"].read_text())["permissions"] == {
        "allow": ["mcp__ratifact__get_context", "Bash(git status:*)"], "deny": ["mcp__ratifact__register_project"]}
    agentes = (maquina["repo"] / "AGENTS.md").read_text()
    assert "uses the `ratifact` MCP server with project `demo`" in agentes and "memoria-proyectos" not in agentes
    assert agentes.endswith("Test command (from the repository root): `pytest`\n")
    assert (maquina["repo"] / "CLAUDE.md").is_symlink()                     # the link is kept, its target edited
    assert "memoria-proyectos" in (maquina["otro"] / "AGENTS.md").read_text()
    home = maquina["home"]
    for destino, objetivo in ((".claude/skills/run-task", "run-task"),
                              (".pi/agent/prompts/run-task.md", "run-task/SKILL.md"),
                              (".codex/skills/run-task", "run-task"),
                              (".agents/skills/run-task", "run-task")):
        assert (home / destino).is_symlink() and Path(os.readlink(home / destino)) == paquete / "skills" / objetivo
    assert not (home / ".claude/commands/run-task.md").exists()               # old own command link: removed
    assert f"remove stale /run-task command link: {home / '.claude/commands/run-task.md'}" in salida
    assert not (home / ".agents/skills/tarea").is_symlink() and (home / ".agents/skills/tarea").is_dir()
    assert not any((home / d).exists() for d in (".claude/commands/tarea.md", ".codex/skills/tarea"))
    assert "Claude Desktop" in salida and "requires approval" in salida      # what cannot be migrated
    assert f"{home / '.agents/skills/tarea'} is not a ratifact /tarea link: left untouched" in salida
    assert "Restart the clients" in salida and "verify with `ratifact doctor`" in salida      # T-016 (ADR-037 §6)
    for ruta in (maquina["desktop"], maquina["pi"], maquina["codex"], maquina["ajustes"], maquina["claude_json"]):
        assert list(ruta.parent.glob(ruta.name + ".bak-ratifact-*")), ruta

    antes = arbol(home)
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=falso)
    assert codigo == 0 and "Nothing to do: everything is already installed." in salida, salida
    assert arbol(home) == antes and len(falso.llamadas) == 2


def test_client_limita_a_uno(maquina, paquete, capsys):
    pi_antes, codex_antes = maquina["pi"].read_text(), maquina["codex"].read_text()
    codigo, salida = instalar(capsys, paquete, aplicar=True, cliente="claude-desktop")
    assert codigo == 0, salida
    assert "ratifact" in json.loads(maquina["desktop"].read_text())["mcpServers"]
    assert maquina["pi"].read_text() == pi_antes and maquina["codex"].read_text() == codex_antes
    assert "Pi:" not in salida and "mcp__ratifact" not in maquina["ajustes"].read_text()
    assert not (maquina["home"] / ".codex/skills/run-task").exists()


def test_error_en_un_cliente_no_detiene_los_demas(maquina, paquete, capsys):
    maquina["desktop"].write_text('{"mcpServers": {,}}')
    codigo, salida = instalar(capsys, paquete, aplicar=True)
    assert codigo == 1 and "not valid JSON" in salida
    assert maquina["desktop"].read_text() == '{"mcpServers": {,}}'
    assert "ratifact" in json.loads(maquina["pi"].read_text())["mcpServers"]


def test_sin_ejecutable_instalado_no_aplica(maquina, paquete, capsys, monkeypatch):
    from ratifact import instalar as modulo
    monkeypatch.setattr(modulo, "ejecutable_instalado", lambda: (None, "not installed: run `uv tool install`"))
    antes = arbol(maquina["home"])
    codigo = modulo.main(aplicar=True, paquete=paquete, claude=None, procesos=lambda: [])
    salida = capsys.readouterr().out
    assert codigo == 1 and "uv tool install" in salida and arbol(maquina["home"]) == antes


def test_desde_la_copia_de_trabajo_no_enlaza_ni_aplica(maquina, capsys):
    antes = arbol(maquina["home"])
    codigo, salida = instalar(capsys, RAIZ_REPO / "ratifact", aplicar=True)
    assert codigo == 1 and "working copy" in salida and arbol(maquina["home"]) == antes


def test_integraciones_se_informan_sin_preguntar(maquina, paquete, capsys):
    codigo, salida = instalar(capsys, paquete)
    bloque = salida.split("Integrations")[1]
    assert "demo: codegraph (detected)" in bloque and "otro: codegraph (off)" in bloque
    assert 'update_project("<project>", integrations="codegraph=off")' in bloque and "engram" in bloque
    assert "?" not in bloque


def test_desde_cero_crea_projects_json_y_doctor_queda_sin_pendientes(casa, paquete, capsys, monkeypatch):
    """Criterion 5, end to end in an empty HOME: install → register_project → doctor = "Pending actions: none"."""
    config = casa / ".config" / "ratifact" / "projects.json"
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)       # no `claude` on this machine: nothing to link
    codigo, salida = instalar(capsys, paquete, aplicar=True)
    assert codigo == 0 and json.loads(config.read_text()) == {}, salida
    assert "Pi: not found (skipped)" in salida
    srv = recargar_servidor()
    salida = srv.register_project(name="nuevo", path=str(crear_repo(casa / "Projects" / "nuevo")))
    assert not salida.startswith("ERROR") and "the `ratifact` MCP server" in salida, salida
    entrada = json.loads(config.read_text())["nuevo"]
    assert set(entrada) == {"path", "memory", "writable", "tests"}
    assert entrada["memory"] == str(casa / "Projects" / ".ratifact" / "nuevo")
    assert "ratifact install --apply" in salida and "ln -s" not in salida
    from ratifact import doctor
    codigo = doctor.main(procesos=lambda: [], paquete=paquete, log_viejo=None)
    salida = capsys.readouterr().out
    assert "Pending actions: none" in salida and codigo == 0, salida
    assert "Claude Desktop: not found" in salida


def test_no_crea_projects_json_si_hay_una_configuracion_vieja(casa, paquete, capsys):
    vieja = _json(casa / ".config/memoria-proyectos/projects.json", {})
    codigo, salida = instalar(capsys, paquete, aplicar=True)
    assert not (casa / ".config/ratifact/projects.json").exists() and "ratifact upgrade" in salida
    assert vieja.read_text() == "{}"


def test_doctor_informa_el_estado_de_cada_cliente(maquina, paquete, capsys):
    from ratifact import doctor
    from ratifact import instalar as modulo
    codigo = doctor.main(procesos=lambda: [], paquete=paquete, log_viejo=None)
    salida = capsys.readouterr().out
    assert codigo == 1 and "Claude Desktop: old configuration" in salida and "Pi: not configured" in salida
    assert "run `ratifact install --apply`" in salida
    assert "remove stale /run-task command link" in salida                   # → the old working-copy link
    modulo.main(aplicar=True, ejecutable=EXE, paquete=paquete, claude=None, procesos=lambda: [])
    capsys.readouterr()
    doctor.main(procesos=lambda: [], paquete=paquete, log_viejo=None)
    salida = capsys.readouterr().out
    assert "Claude Desktop: configured with ratifact" in salida and "Codex: configured with ratifact" in salida
    assert "/run-task links: ok" in salida


def test_bloque_actual_de_un_proyecto_llamado_memoria_proyectos_no_es_un_paso_manual(tmp_path):
    from ratifact.instalar_extras import planificar_bloques
    from ratifact.plantillas import PLANTILLA_AGENTES, PLANTILLA_AGENTES_V1
    (tmp_path / "AGENTS.md").write_text(PLANTILLA_AGENTES.format(proyecto="memoria-proyectos") + "\n")
    assert planificar_bloques([("memoria-proyectos", tmp_path, [])]) == ([], [])
    (tmp_path / "AGENTS.md").write_text(PLANTILLA_AGENTES_V1.format(proyecto="memoria-proyectos") + "\n")
    cambios, manuales = planificar_bloques([("memoria-proyectos", tmp_path, [])])
    assert len(cambios) == 1 and not manuales
    assert cambios[0].texto == PLANTILLA_AGENTES.format(proyecto="memoria-proyectos") + "\n"


# ───────────────────────── backups of repository files go to the state dir ─────────────────────────

def _respaldos(casa: Path) -> Path:
    import datetime as dt
    return casa / ".local" / "state" / "ratifact" / "backups" / dt.date.today().isoformat()


def test_respaldos_de_archivos_de_proyecto_van_al_directorio_de_estado(maquina, paquete, capsys):
    repo, otro = maquina["repo"], maquina["otro"]
    antes_repo = {p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts}
    antes_otro = {p.relative_to(otro) for p in otro.rglob("*") if ".git" not in p.parts}
    agentes_antes, ajustes_antes = (repo / "AGENTS.md").read_text(), maquina["proyecto"].read_text()
    codigo, salida = instalar(capsys, paquete, aplicar=True)
    assert codigo == 0, salida
    assert {p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts} == antes_repo   # no new file
    assert {p.relative_to(otro) for p in otro.rglob("*") if ".git" not in p.parts} == antes_otro
    destino = _respaldos(maquina["home"])
    agentes = destino / str(repo / "AGENTS.md").lstrip("/")
    ajustes = destino / str(maquina["proyecto"]).lstrip("/")
    assert agentes.read_text() == agentes_antes and ajustes.read_text() == ajustes_antes
    # an untouched hand-written block (otro/AGENTS.md) has no backup anywhere
    assert not list(destino.rglob("*otro*AGENTS.md*")) and not list(otro.glob("*.bak-ratifact-*"))
    # client files outside repositories keep <file>.bak-ratifact-<date> next to them
    assert list(maquina["ajustes"].parent.glob("settings.json.bak-ratifact-*"))
    assert list(maquina["desktop"].parent.glob("*.bak-ratifact-*"))
    assert str(destino.parent) in salida or "backups" in salida


def test_plan_dice_donde_van_los_respaldos_de_los_repositorios(maquina, paquete, capsys):
    _, salida = instalar(capsys, paquete)
    assert str(maquina["home"] / ".local" / "state" / "ratifact" / "backups") in salida


def test_respaldo_repetido_el_mismo_dia_no_pisa_el_anterior(tmp_path, monkeypatch):
    from ratifact import archivos
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "estado"))
    ruta = tmp_path / "repo" / "AGENTS.md"
    ruta.parent.mkdir()
    ruta.write_text("uno")
    primero = archivos.escribir_validado(ruta, "dos", lambda t: None, en_estado=True)
    segundo = archivos.escribir_validado(ruta, "tres", lambda t: None, en_estado=True)
    assert primero != segundo and primero.read_text() == "uno" and segundo.read_text() == "dos"
    assert primero.parent == segundo.parent and str(ruta).lstrip("/") in str(primero)
    assert sorted(p.name for p in ruta.parent.iterdir()) == ["AGENTS.md"]


# ───────────── T-017: the /tarea alias is retired (ADR-039) and /run-task links are verified ─────────────

def _enlazar(ruta, destino):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.symlink_to(destino)
    return ruta


def test_el_paquete_ya_no_trae_tarea():
    assert not (RAIZ_REPO / "ratifact" / "skills" / "tarea").exists() and not (RAIZ_REPO / "tarea.md").exists()
    assert (RAIZ_REPO / "ratifact" / "skills" / "run-task" / "SKILL.md").is_file()


def test_la_rueda_no_incluye_skills_tarea(tmp_path):
    import zipfile
    salida = tmp_path / "dist"
    try:
        r = subprocess.run(["uv", "build", "--wheel", "-o", str(salida)], cwd=RAIZ_REPO, capture_output=True,
                           text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        pytest.skip(f"uv build unavailable: {e}")
    if r.returncode != 0:
        pytest.skip(f"uv build failed (offline?): {r.stderr[-200:]}")
    rueda = next(salida.glob("*.whl"))
    nombres = zipfile.ZipFile(rueda).namelist()
    assert any(n.endswith("skills/run-task/SKILL.md") for n in nombres)
    assert not [n for n in nombres if "skills/tarea" in n]


@pytest.fixture
def cliente_configurado(casa, paquete, capsys):
    """Claude Code, Pi and Codex configured with the ratifact server and all their /run-task links in place."""
    falso = ClaudeFalso(casa / ".claude.json")
    (casa / ".pi/agent").mkdir(parents=True)
    (casa / ".codex").mkdir()
    (casa / ".claude.json").write_text("{}")
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=falso)
    assert codigo == 0, salida
    return falso


def test_install_no_crea_enlaces_tarea(cliente_configurado, casa, paquete, capsys):
    assert (casa / ".claude/skills/run-task").is_symlink() and not (casa / ".claude/commands/run-task.md").exists()
    assert not [p for p in casa.rglob("*tarea*") if "Projects" not in p.parts]
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert "remove stale" not in salida and "Nothing to do: everything is already installed." in salida


def test_plan_anuncia_y_apply_borra_el_enlace_propio_obsoleto(casa, paquete, capsys):
    propio = _enlazar(casa / ".codex/skills/tarea", paquete / "skills" / "tarea")            # broken: no such folder
    otro = _enlazar(casa / ".claude/commands/tarea.md", paquete / "skills" / "tarea" / "SKILL.md")
    codigo, salida = instalar(capsys, paquete, claude=None)
    assert f"remove stale /tarea link: {propio}" in salida and f"remove stale /tarea link: {otro}" in salida
    assert "Nothing to do" not in salida and propio.is_symlink()                              # the plan changes nothing
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude=None)
    assert codigo == 0 and not propio.is_symlink() and not otro.is_symlink(), salida
    assert not propio.exists() and not otro.exists()


def test_checkout_de_ratifact_tambien_cuenta_como_propio(casa, paquete, capsys):
    repo = casa / "dev" / "repo"
    (repo / "ratifact").mkdir(parents=True)
    (repo / "ratifact" / "__init__.py").write_text("")
    enlace = _enlazar(casa / ".agents/skills/tarea", repo / "skills" / "tarea")
    instalar(capsys, paquete, aplicar=True, claude=None)
    assert not enlace.is_symlink()


def test_archivo_real_y_enlace_ajeno_llamados_tarea_se_conservan(casa, paquete, capsys):
    real = casa / ".claude/commands/tarea.md"
    real.parent.mkdir(parents=True)
    real.write_text("mine")
    ajeno = _enlazar(casa / ".codex/skills/tarea", casa / "otra-cosa" / "tarea")
    sospechoso = _enlazar(casa / ".agents/skills/tarea", casa / "x" / "skills" / "tarea")     # not a ratifact tree
    codigo, salida = instalar(capsys, paquete)
    for ruta in (real, ajeno, sospechoso):
        assert f"{ruta} is not a ratifact /tarea link: left untouched" in salida, salida
    assert "remove stale" not in salida
    instalar(capsys, paquete, aplicar=True)
    assert real.read_text() == "mine" and ajeno.is_symlink() and sospechoso.is_symlink()
    assert os.readlink(ajeno) == str(casa / "otra-cosa" / "tarea")


def test_upgrade_apply_borra_el_enlace_propio_obsoleto(casa, paquete, capsys):
    propio = _enlazar(casa / ".claude/skills/tarea", paquete / "skills" / "tarea")
    real = casa / ".pi/agent/prompts/tarea.md"
    real.parent.mkdir(parents=True)
    real.write_text("mine")
    (casa / ".config/ratifact").mkdir(parents=True)
    (casa / ".config/ratifact/projects.json").write_text("{}")
    from ratifact import upgrade
    assert upgrade.main(aplicar=False, procesos=lambda: []) == 0
    salida = capsys.readouterr().out
    assert f"remove stale /tarea link: {propio}" in salida and "left untouched" in salida and propio.is_symlink()
    assert upgrade.main(aplicar=True, procesos=lambda: []) == 0
    capsys.readouterr()
    assert not propio.is_symlink() and real.read_text() == "mine"


def test_cliente_configurado_sin_enlace_run_task_no_dice_nada_que_hacer(cliente_configurado, casa, paquete, capsys):
    enlace = casa / ".claude/skills/run-task"
    enlace.unlink()
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert f"link /run-task: {enlace} → {paquete / 'skills' / 'run-task'}" in salida
    assert "Nothing to do" not in salida
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert enlace.is_symlink() and Path(os.readlink(enlace)) == paquete / "skills" / "run-task"


def test_enlace_run_task_roto_se_reemplaza(cliente_configurado, casa, paquete, capsys):
    enlace = casa / ".codex/skills/run-task"
    enlace.unlink()
    enlace.symlink_to(casa / "no-existe" / "run-task")
    codigo, salida = instalar(capsys, paquete, claude="/usr/bin/claude")
    assert f"relink /run-task: {enlace}" in salida and "Nothing to do" not in salida
    instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert Path(os.readlink(enlace)) == paquete / "skills" / "run-task" and enlace.exists()


def test_carpeta_real_en_la_ruta_de_run_task_se_conserva_con_aviso(cliente_configurado, casa, paquete, capsys):
    enlace = casa / ".claude/skills/run-task"
    enlace.unlink()
    enlace.mkdir()
    (enlace / "SKILL.md").write_text("mine")
    codigo, salida = instalar(capsys, paquete, aplicar=True, claude="/usr/bin/claude", correr=cliente_configurado)
    assert f"{enlace} exists and is not a link" in salida
    assert enlace.is_dir() and not enlace.is_symlink() and (enlace / "SKILL.md").read_text() == "mine"


def test_enlace_a_una_carpeta_ratifact_ajena_se_conserva_y_el_roto_en_site_packages_se_borra(casa, paquete, capsys):
    ajena = casa / "u" / "ratifact" / "skills" / "tarea"          # no __init__.py, not under site-packages
    ajeno = _enlazar(casa / ".codex/skills/tarea", ajena)
    propio = _enlazar(casa / ".agents/skills/tarea", casa / "venv" / "site-packages" / "ratifact" / "skills" / "tarea")
    codigo, salida = instalar(capsys, paquete)
    assert f"{ajeno} is not a ratifact /tarea link: left untouched" in salida
    assert f"remove stale /tarea link: {propio}" in salida and f"remove stale /tarea link: {ajeno}" not in salida
    instalar(capsys, paquete, aplicar=True)
    assert ajeno.is_symlink() and not propio.is_symlink()


def test_upgrade_solo_con_enlace_obsoleto_no_se_bloquea_por_un_servidor(casa, paquete, capsys):
    propio = _enlazar(casa / ".claude/skills/tarea", paquete / "skills" / "tarea")
    config = casa / ".config/ratifact/projects.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    from ratifact import upgrade
    from ratifact.instalacion import Proceso
    procesos = lambda: [Proceso(4242, "ratifact serve", config)]
    codigo = upgrade.main(aplicar=True, procesos=procesos, log_viejo=casa / "sin-log.jsonl")
    salida = capsys.readouterr().out
    assert codigo == 0 and "server running" not in salida and not propio.is_symlink(), salida
