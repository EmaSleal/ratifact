"""Comando `ratifact` (T-012): versión, subcomandos, `report` (antes analizar_uso.py), `doctor` de solo lectura con sus
acciones pendientes y código de salida, y el respaldo de configuración tras el upgrade."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import RAIZ_REPO, recargar_servidor
from test_analizar_uso import _escribir_log
from test_upgrade import arbol, correr, hogar, vieja  # noqa: F401,F811  (fixtures)


def test_version_igual_en_pyproject_y_en_el_paquete(capsys):
    import ratifact
    from ratifact import cli
    pyproject = (RAIZ_REPO / "pyproject.toml").read_text()
    assert re.search(r'^version = "(.+)"$', pyproject, re.M).group(1) == ratifact.__version__ == "1.0.0"
    assert 'ratifact = "ratifact.cli:main"' in pyproject and 'name = "ratifact"' in pyproject
    with pytest.raises(SystemExit) as salida:
        cli.main(["--version"])
    assert salida.value.code == 0 and capsys.readouterr().out.strip() == "ratifact 1.0.0"


def test_subcomandos_en_la_ayuda(capsys):
    from ratifact import cli
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    salida = capsys.readouterr().out
    assert all(c in salida for c in ("serve", "report", "doctor", "upgrade"))
    with pytest.raises(SystemExit) as error:
        cli.main([])
    assert error.value.code == 2


def test_report_con_opciones_en_ingles(entorno, capsys):
    from ratifact import cli
    _escribir_log(Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]), "get_context")
    cli.main(["report", "--days", "3", "--project", "demo"])
    salida = capsys.readouterr().out
    assert "last 3 days" in salida and "get_context" in salida


def test_analizar_uso_sigue_como_envoltorio(entorno):
    _escribir_log(Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]), "search")
    import os
    r = subprocess.run([sys.executable, str(RAIZ_REPO / "analizar_uso.py"), "--dias", "2"], capture_output=True,
                       text=True, env={**os.environ, **entorno["env"]})
    assert r.returncode == 0 and "last 2 days" in r.stdout and "search" in r.stdout


def _doctor(vieja, capsys, paquete=None):
    from ratifact import doctor
    codigo = doctor.main(procesos=lambda: [], paquete=paquete, log_viejo=vieja["log"])
    return codigo, capsys.readouterr().out


def test_doctor_informa_y_no_escribe_nada(vieja, entorno, capsys):
    antes = arbol(entorno["tmp"])
    codigo, salida = _doctor(vieja, capsys)
    assert arbol(entorno["tmp"]) == antes
    assert codigo == 1
    base = vieja["base"]
    for esperado in ("ratifact 1.0.0", f"Running from: working copy {RAIZ_REPO}", "changes in the working tree reach the clients immediately",
                     f"Configuration: {vieja['config']} (from MEMORIA_PROYECTOS_CONFIG (deprecated))",
                     "Keys in projects.json: Spanish",
                     f"memory: {base / '.memorias' / 'uno'} · schema v1 · old default (.memorias/) · git: clean",
                     f"memory: {base / 'juego' / '.project'} · schema v1 · custom path · git: clean",
                     f"memory: {base / '.memorias' / 'dos'} · schema v2 · old default (.memorias/)",
                     "integrations: codegraph (off)", "Usage log:", f"Old usage log: {vieja['log']}",
                     "Deprecated variables: MEMORIA_PROYECTOS_CONFIG, MEMORIA_PROYECTOS_LOG, MEMORIA_PROYECTOS_BASE",
                     "Pending actions:", "run `ratifact upgrade`", "2. move uno",
                     "MEMORIA_PROYECTOS_CONFIG is deprecated (removed in 1.1): rename it to RATIFACT_CONFIG"):
        assert esperado in salida, (esperado, salida)


def test_doctor_detecta_integraciones_y_memoria_sucia(vieja, capsys):
    (vieja["base"] / "uno" / "codigo" / ".atl").mkdir()
    (vieja["base"] / ".memorias" / "uno" / "x.md").write_text("x")
    codigo, salida = _doctor(vieja, capsys)
    assert codigo == 1 and "integrations: gentle-ai (detected)" in salida
    assert "uno: memory" in salida and "uncommitted changes (x.md)" in salida


def test_doctor_sin_pendientes_tras_el_upgrade_sale_con_0(vieja, entorno, capsys, monkeypatch, tmp_path):
    assert correr(vieja, capsys, aplicar=True)[0] == 0
    for sufijo in ("CONFIG", "LOG", "BASE"):
        valor = entorno["env"][f"MEMORIA_PROYECTOS_{sufijo}"]
        monkeypatch.delenv(f"MEMORIA_PROYECTOS_{sufijo}")
        if sufijo != "CONFIG":
            monkeypatch.setenv(f"RATIFACT_{sufijo}", valor)
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)       # sin `claude`: no hay enlaces que exigir
    instalado = tmp_path / "site-packages" / "ratifact"       # instalación fija (no es la copia de trabajo)
    instalado.mkdir(parents=True)
    antes = arbol(entorno["tmp"])
    codigo, salida = _doctor(vieja, capsys, paquete=instalado)
    assert arbol(entorno["tmp"]) == antes
    assert f"Running from: fixed installation {instalado}" in salida
    assert f"Configuration: {vieja['nueva']} (from default)" in salida and "Keys in projects.json: English" in salida
    assert "new default (.ratifact/)" in salida and "Pending actions: none" in salida and codigo == 0, salida


def test_doctor_avisa_si_la_variable_apunta_al_archivo_renombrado(vieja, capsys):
    assert correr(vieja, capsys, aplicar=True)[0] == 0
    codigo, salida = _doctor(vieja, capsys)
    assert f"Configuration: {vieja['nueva']}" in salida
    assert f"the CONFIG variable points to {vieja['config']}, which `ratifact upgrade` renamed" in salida
    assert codigo == 1


def test_deteccion_de_procesos_del_servidor():
    from ratifact.instalacion import _es_servidor
    for args in (["/usr/bin/uv", "run", "--script", "/r/servidor.py"], ["/venv/bin/python3", "/r/servidor.py"],
                 ["/home/u/.local/bin/ratifact", "serve"], ["uvx", "ratifact", "serve"],
                 ["python3", "-m", "ratifact.cli", "serve"], ["/venv/bin/python", "/venv/bin/ratifact", "serve"]):
        assert _es_servidor(args), args
    for args in (["nvim", "servidor.py"], ["bat", "/r/servidor.py"], ["ratifact", "upgrade", "--apply"],
                 ["ratifact", "doctor"], ["python3", "/r/analizar_uso.py"], []):
        assert not _es_servidor(args), args


def test_procesos_se_separan_por_configuracion(tmp_path):
    from ratifact.instalacion import Proceso, _config_de, separar_procesos
    config = tmp_path / "projects.json"
    config.write_text("{}")
    propio, otro, desconocido = Proceso(1, "a", config), Proceso(2, "b", tmp_path / "otro.json"), Proceso(3, "c", None)
    assert separar_procesos([propio, otro, desconocido], config) == ([propio, desconocido], [otro])
    assert _config_de({"HOME": str(tmp_path), "MEMORIA_PROYECTOS_CONFIG": str(config)}, None) == config
    assert _config_de({"HOME": str(tmp_path)}, None) == tmp_path / ".config" / "memoria-proyectos" / "projects.json"


def test_update_project_escribe_integrations_en_una_entrada_inglesa(srv, proyecto, entorno):
    import json
    config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    datos = json.loads(config.read_text())
    datos["demo"] = {{"ruta": "path", "memoria": "memory", "escritura": "writable", "pruebas": "tests"}.get(k, k): v
                     for k, v in datos["demo"].items()}
    config.write_text(json.dumps(datos))
    assert not srv.update_project(name="demo", integrations="codegraph=off").startswith("ERROR")
    entrada = json.loads(config.read_text())["demo"]
    assert entrada["integrations"] == {"codegraph": "off"} and "integraciones" not in entrada
    (proyecto["repo"] / ".codegraph").mkdir()
    assert "codegraph" not in srv.get_context(project="demo")


def test_doctor_no_pide_upgrade_despues_de_registrar_un_proyecto_nuevo(vieja, entorno, capsys, monkeypatch, tmp_path):
    """Criterio 15: tras el upgrade, un proyecto nuevo nace en <base>/.ratifact/<p> y doctor no pide otro upgrade."""
    assert correr(vieja, capsys, aplicar=True)[0] == 0
    for sufijo in ("CONFIG", "LOG", "BASE"):
        valor = entorno["env"][f"MEMORIA_PROYECTOS_{sufijo}"]
        monkeypatch.delenv(f"MEMORIA_PROYECTOS_{sufijo}")
        if sufijo != "CONFIG":
            monkeypatch.setenv(f"RATIFACT_{sufijo}", valor)
    srv = recargar_servidor()
    from conftest import crear_repo
    salida = srv.register_project(name="nuevo", path=str(crear_repo(vieja["base"] / "nuevo" / "codigo")))
    assert not salida.startswith("ERROR"), salida
    assert json.loads(vieja["nueva"].read_text())["nuevo"]["memory"] == str(vieja["base"] / ".ratifact" / "nuevo")
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)
    instalado = tmp_path / "site-packages" / "ratifact"
    instalado.mkdir(parents=True)
    codigo, salida = _doctor(vieja, capsys, paquete=instalado)
    assert f"memory: {vieja['base'] / '.ratifact' / 'nuevo'} · schema v2 · new default (.ratifact/)" in salida
    assert "run `ratifact upgrade`" not in salida and "Pending actions: none" in salida and codigo == 0, salida


# ───────────── T-017: doctor and the /run-task links / retired /tarea alias ─────────────

def test_doctor_avisa_de_un_enlace_tarea_que_sigue_presente(vieja, hogar, capsys, tmp_path):
    instalado = tmp_path / "site-packages" / "ratifact"
    instalado.mkdir(parents=True)
    propio = hogar / ".codex" / "skills" / "tarea"
    propio.parent.mkdir(parents=True)
    propio.symlink_to(instalado / "skills" / "tarea")
    ajeno = hogar / ".agents" / "skills" / "tarea"
    ajeno.parent.mkdir(parents=True)
    ajeno.mkdir()
    codigo, salida = _doctor(vieja, capsys, paquete=instalado)
    assert f"remove stale /tarea link: {propio}: run `ratifact install --apply`" in salida
    assert f"{ajeno} is not a ratifact /tarea link: left untouched (remove it by hand" in salida
    assert codigo == 1 and propio.is_symlink()                      # read-only


def test_doctor_detecta_el_enlace_run_task_ausente_o_roto(vieja, hogar, capsys, tmp_path, monkeypatch):
    instalado = tmp_path / "site-packages" / "ratifact"
    (instalado / "skills" / "run-task").mkdir(parents=True)
    (hogar / ".codex").mkdir()
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)
    codigo, salida = _doctor(vieja, capsys, paquete=instalado)
    assert "/run-task link(s) are missing" in salida and "run `ratifact install --apply`" in salida
    assert "/run-task links: 2 missing" in salida
    roto = hogar / ".codex" / "skills" / "run-task"
    roto.parent.mkdir(parents=True)
    roto.symlink_to(hogar / "no-existe")
    codigo, salida = _doctor(vieja, capsys, paquete=instalado)
    assert "point elsewhere or are broken" in salida and "1 missing, 1 pointing elsewhere" in salida
