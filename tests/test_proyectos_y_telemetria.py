"""Alta de proyectos, instrucciones generadas, memoria en repo propio y telemetría."""
import json
import re
from pathlib import Path

from conftest import crear_repo, log_git, RAIZ_REPO
from ratifact.herramientas import pendientes_sesiones


def test_alta_crea_memoria_con_repo_propio_e_instrucciones(srv, proyecto, entorno):
    assert (proyecto["mem"] / ".git").exists()
    assert "memoria: inicializar memoria" in log_git(proyecto["mem"])
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["demo"]["memory"] == str(proyecto["mem"])
    instr = srv.project_instructions(project="demo")
    assert "project: demo" in instr and 'get_context("demo")' in instr


def test_alta_valida_nombre_rutas_y_duplicados(srv, proyecto, entorno):
    otro = crear_repo(entorno["base"] / "otro")
    assert "Invalid name" in srv.register_project(name="Mi Proyecto", path=str(otro))
    assert "inside" in srv.register_project(name="otro", path="/tmp")
    assert "does not exist" in srv.register_project(name="otro", path=str(entorno["base"] / "nada"))
    assert "is already registered" in srv.register_project(name="demo", path=str(otro))
    assert "is not registered" in srv.project_instructions(project="nada")


def test_alta_sin_git_avisa(srv, entorno):
    (entorno["base"] / "suelto").mkdir()
    assert "is not a git repository" in srv.register_project(name="suelto", path=str(entorno["base"] / "suelto"))


def test_memoria_dentro_del_repo_del_codigo_se_rechaza(srv, entorno):
    """ADR-010: un solo modo; la memoria nunca vive dentro del repositorio del código."""
    repo = crear_repo(entorno["base"] / "interno")
    salida = srv.register_project(name="interno", path=str(repo), memory=str(repo / ".project"))
    assert "inside the code repository" in salida and "published with the code" in salida and "interno" not in srv.list_projects()


def test_memoria_dentro_del_repo_mensaje_de_alta_distinto_de_actualizar(srv, entorno):
    """Obs. 4 / Criterio E: register_project sugiere omitir `memoria` (no existe aún una memoria elegida
    para "corregir"); update_project, en cambio, usa la redacción de corrección (ver
    tests/test_actualizar_proyecto.py::test_actualizar_ruta_rechaza_memoria_adentro_adr010 para su mensaje)."""
    repo = crear_repo(entorno["base"] / "interno3")
    salida = srv.register_project(name="interno3", path=str(repo), memory=str(repo / ".project"))
    assert "inside the code repository" in salida and "published with the code" in salida
    assert "omit `memory`" in salida
    assert "not supported here" not in salida


def test_config_heredada_con_memoria_interna_avisa_como_migrar(srv, entorno):
    repo = crear_repo(entorno["base"] / "viejo")
    Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).write_text(json.dumps(
        {"viejo": {"ruta": str(repo), "memoria": str(repo / ".project")}}))
    salida = srv.add_pending(project="viejo", topic="t", context="c")
    assert salida.startswith("ERROR:") and ".ratifact/viejo" in salida
    assert "invalid configuration" in srv.list_projects()


def test_sin_clave_memoria_usa_ratifact_por_defecto(srv, entorno):
    """T-012 (criterio 15): la ruta por defecto de una memoria nueva es <base>/.ratifact/<nombre>."""
    repo = crear_repo(entorno["base"] / "legado")
    Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).write_text(json.dumps({"legado": {"ruta": str(repo)}}))
    srv.init_memory(project="legado")
    assert (entorno["base"] / ".ratifact" / "legado" / ".git").exists() and not (repo / ".project").exists()
    assert not (entorno["base"] / ".memorias" / "legado").exists()


def test_sin_clave_memoria_la_vieja_en_memorias_se_sigue_encontrando(srv, entorno):
    """Un proyecto sin ruta de memoria explícita cuya memoria ya existe en <base>/.memorias/<p> se sigue usando ahí
    hasta que `ratifact upgrade` la mueve; no se crea otra en .ratifact/."""
    repo = crear_repo(entorno["base"] / "legado")
    Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).write_text(json.dumps({"legado": {"ruta": str(repo)}}))
    vieja = entorno["base"] / ".memorias" / "legado"
    vieja.mkdir(parents=True)
    srv.init_memory(project="legado")
    assert "P-001 recorded" in srv.add_pending(project="legado", topic="t", context="c")
    assert list((vieja / "pending").glob("P-001-*.md")) and not (entorno["base"] / ".ratifact" / "legado").exists()


def test_inicializar_es_idempotente(srv, proyecto):
    assert not srv.init_memory(project="demo").startswith("ERROR")
    assert "memory ready" in srv.list_projects()


def test_telemetria_registra_y_clasifica_errores(srv, proyecto, entorno):
    srv.get_context(project="demo")
    srv.accept_decision(project="demo", id="ADR-404", user_quote="ok")    # rechazo de validación
    srv.read_document(project="demo", path="docs/vision.md")
    filas = [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]
    ultimas = {f["herramienta"]: f for f in filas}
    assert ultimas["get_context"]["error"] is False and ultimas["get_context"]["resp_chars"] > 0
    assert ultimas["accept_decision"]["tipo_error"] == "validacion"
    assert ultimas["read_document"]["ruta"] == "docs/vision.md"
    assert all("contenido" not in f.get("args_chars", {}) or isinstance(f["args_chars"]["contenido"], int) for f in filas)


def test_falla_inesperada_se_registra_como_interna(srv, proyecto, entorno, monkeypatch):
    def rota(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(pendientes_sesiones, "_regenerar_vistas", rota)
    salida = srv.add_pending(project="demo", topic="t", context="c")
    assert salida.startswith("ERROR (internal): OSError")
    fila = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()[-1])
    assert fila["tipo_error"] == "interno"


def test_sin_nombres_de_proyecto_fijos_en_el_codigo():
    """Regresión: 'game' como valor por defecto hizo que 'inicio' cargara otro proyecto."""
    codigo = "\n".join(p.read_text() for p in [RAIZ_REPO / "servidor.py", *sorted((RAIZ_REPO / "ratifact").rglob("*.py"))])
    sin_docstring = codigo.split('"""', 2)[2]
    assert "game" not in sin_docstring
    assert not re.search(r'proyecto: str = "[^"]+"', sin_docstring)
    assert not re.search(r'project: str = "[^"]+"', sin_docstring)


def test_instrucciones_cubren_codex(srv, proyecto):
    """ADR-008: Codex no tiene comandos propios (custom prompts eliminados); /run-task se instala como skill."""
    salida = srv.project_instructions(project="demo")
    assert "ratifact install --apply" in salida and "the whole folder for Codex" in salida     # T-013
    assert "$run-task T-NNN" in salida and "/tarea" not in salida
    raiz = srv.Path(srv.__file__).parent
    for nombre in ("run-task",):
        skill = raiz / "skills" / nombre / "SKILL.md"
        assert skill.is_file() and not skill.is_symlink()                   # Codex no sigue SKILL.md enlazados
        assert (raiz / f"{nombre}.md").resolve() == skill.resolve()       # una sola fuente
        cabecera = skill.read_text().split("---")[1]
        assert f"name: {nombre}" in cabecera and "description:" in cabecera      # requisitos de una skill de Codex


def test_servidor_se_declara_fuente_de_verdad(srv):
    """Hallazgo Codex/Fractall: con engram presente, "carga el contexto" consultó solo engram. T-008: la regla es
    genérica (cualquier otra memoria de agente); lo específico de engram vive en su integración."""
    texto = srv.mcp.instructions
    assert "get_context" in texto and "other agent memories" in texto and "this server wins" in texto
