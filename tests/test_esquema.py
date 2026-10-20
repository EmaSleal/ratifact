"""Versión de esquema de la memoria: toda memoria declara su formato; las antiguas se migran solas y las más
nuevas que el servidor no se tocan (requisito para distribuir sin romper instalaciones existentes)."""
import json
import subprocess

from conftest import log_git
from ratifact import esquema


def _version(mem):
    return json.loads((mem / "schema.json").read_text())["version"]


def _quitar_esquema(mem):
    """Simula una memoria creada antes del versionado (v0): una v1 sin esquema.json."""
    subprocess.run(["git", "-C", str(mem), "rm", "-q", "esquema.json"], check=True)
    subprocess.run(["git", "-C", str(mem), "commit", "-q", "-m", "memoria antigua"], check=True)


def test_memoria_nueva_declara_la_version(srv, proyecto):
    mem = proyecto["mem"]
    assert json.loads((mem / "schema.json").read_text()) == {"version": srv.VERSION_ESQUEMA, "content_language": "en"}
    assert json.loads((mem / "esquema.json").read_text()) == {"version": srv.VERSION_ESQUEMA}    # centinela ADR-030
    salida = subprocess.run(["git", "-C", str(mem), "ls-files", "schema.json", "esquema.json"],
                            capture_output=True, text=True).stdout
    assert salida.split() == ["esquema.json", "schema.json"]
    assert f"schema v{srv.VERSION_ESQUEMA}]" in srv.list_projects()


def test_memoria_antigua_se_migra_en_la_primera_escritura(srv, proyecto_v1):
    salida = srv.propose_decision(project="demo", title="A", decision="d", rationale="j")
    assert "migrated to schema v2" in salida and "recorded as proposed" in salida
    assert _version(proyecto_v1["mem"]) == srv.VERSION_ESQUEMA
    historial = log_git(proyecto_v1["mem"])
    assert historial[1] == f"memory: migrate schema v1 → v{srv.VERSION_ESQUEMA}"   # migración en commit propio, antes
    assert historial[0].startswith("memoria: ADR-005")


def test_memoria_v0_se_migra_igual(srv, proyecto_v1):
    _quitar_esquema(proyecto_v1["mem"])
    assert not srv.get_context(project="demo").startswith("ERROR")
    assert _version(proyecto_v1["mem"]) == srv.VERSION_ESQUEMA
    assert log_git(proyecto_v1["mem"])[0] == f"memory: migrate schema v0 → v{srv.VERSION_ESQUEMA}"


def test_obtener_contexto_tambien_migra(srv, proyecto_v1):
    assert not srv.get_context(project="demo").startswith("ERROR")
    assert _version(proyecto_v1["mem"]) == srv.VERSION_ESQUEMA


def test_cadena_de_migraciones_en_orden(srv, proyecto_v1, monkeypatch):
    """v1 → v2 (la real) → v3 (simulada) en un solo commit, en orden; ya al día, no se repite."""
    llamadas = []
    real = srv.MIGRACIONES[2]

    def a_v2(mem):
        llamadas.append(2)
        return real(mem)

    def a_v3(mem):
        llamadas.append(3)
        assert (mem / "decisions").is_dir()             # corre después de la v2
        (mem / "nuevo.md").write_text("formato v3\n")
        return ["nuevo.md agregado"]
    monkeypatch.setattr(esquema, "VERSION_ESQUEMA", 3)
    monkeypatch.setattr(esquema, "MIGRACIONES", {**srv.MIGRACIONES, 2: a_v2, 3: a_v3})
    srv.add_pending(project="demo", topic="T", context="c")
    mem = proyecto_v1["mem"]
    assert llamadas == [2, 3] and _version(mem) == 3
    assert json.loads((mem / "esquema.json").read_text()) == {"version": 3}           # el centinela acompaña
    assert json.loads((mem / "schema.json").read_text())["content_language"] == "es"  # memoria migrada
    assert log_git(mem)[1] == "memory: migrate schema v1 → v3"
    assert "nuevo.md agregado" in subprocess.run(["git", "-C", str(mem), "log", "-1", "--skip=1", "--format=%b"],
                                                 capture_output=True, text=True).stdout
    assert "pre-v3" in subprocess.run(["git", "-C", str(mem), "tag"], capture_output=True, text=True).stdout
    assert "nuevo.md" in subprocess.run(["git", "-C", str(mem), "ls-files"], capture_output=True, text=True).stdout
    srv.add_pending(project="demo", topic="T2", context="c")      # ya al día: no migra de nuevo
    assert llamadas == [2, 3]


def test_un_cambio_futuro_desde_v2_conserva_el_idioma(srv, proyecto, monkeypatch):
    monkeypatch.setattr(esquema, "VERSION_ESQUEMA", 3)
    monkeypatch.setattr(esquema, "MIGRACIONES", {**srv.MIGRACIONES, 3: lambda mem: []})
    srv.list_tasks(project="demo")
    assert json.loads((proyecto["mem"] / "schema.json").read_text()) == {"version": 3, "content_language": "en"}
    assert log_git(proyecto["mem"])[0] == "memory: migrate schema v2 → v3"


def test_memoria_mas_nueva_que_el_servidor_no_se_toca(srv, proyecto):
    mem = proyecto["mem"]
    (mem / "schema.json").write_text(json.dumps({"version": srv.VERSION_ESQUEMA + 1, "content_language": "en"}))
    antes = log_git(mem)
    for salida in (srv.propose_decision(project="demo", title="A", decision="d", rationale="j"),
                   srv.get_context(project="demo"), srv.list_tasks(project="demo")):
        assert salida.startswith("ERROR:") and "Update ratifact" in salida
    assert log_git(mem) == antes and not list((mem / "decisions").glob("ADR-*.md"))


def test_schema_json_manda_sobre_esquema_json(srv, proyecto):
    """ADR-030: con schema.json presente, esquema.json no se consulta (aunque diga otra cosa)."""
    (proyecto["mem"] / "esquema.json").write_text('{"version": 1}\n')
    assert esquema._version_esquema(proyecto["mem"]) == srv.VERSION_ESQUEMA


def test_esquema_danado_es_rechazo_legible(srv, proyecto):
    (proyecto["mem"] / "schema.json").write_text("{no es json")
    salida = srv.add_pending(project="demo", topic="T", context="c")
    assert salida.startswith("ERROR:") and "corrupted" in salida


def test_migracion_sin_commit_se_deshace(srv, proyecto_v1, monkeypatch):
    """Hallazgo al migrar Fractall: si git no puede commitear, la migración no debe quedar a medias."""
    mem = proyecto_v1["mem"]
    git_real = esquema._git

    def git_sin_commit(m, *args):
        if args[0] == "commit":
            return subprocess.CompletedProcess(args, 128, "", "Author identity unknown")
        return git_real(m, *args)
    monkeypatch.setattr(esquema, "_git", git_sin_commit)
    antes = log_git(mem)
    salida = srv.add_pending(project="demo", topic="T", context="c")
    assert salida.startswith("ERROR:") and "Author identity unknown" in salida
    assert log_git(mem) == antes and not (mem / "schema.json").exists() and not (mem / "pending").exists()
    assert (mem / "esquema.json").read_text() == '{"version": 1}\n'
    assert not list((mem / "pendientes").glob("P-003*"))
