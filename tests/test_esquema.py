"""Versión de esquema de la memoria: toda memoria declara su formato; las antiguas se migran solas y las más
nuevas que el servidor no se tocan (requisito para distribuir sin romper instalaciones existentes)."""
import json
import subprocess

from conftest import log_git
from ratifact import esquema


def _version(mem):
    return json.loads((mem / "esquema.json").read_text())["version"]


def _quitar_esquema(mem):
    """Simula una memoria creada antes del versionado (v0)."""
    subprocess.run(["git", "-C", str(mem), "rm", "-q", "esquema.json"], check=True)
    subprocess.run(["git", "-C", str(mem), "commit", "-q", "-m", "memoria antigua"], check=True)


def test_memoria_nueva_declara_la_version(srv, proyecto):
    assert _version(proyecto["mem"]) == srv.VERSION_ESQUEMA
    salida = subprocess.run(["git", "-C", str(proyecto["mem"]), "ls-files", "esquema.json"],
                            capture_output=True, text=True).stdout
    assert salida.strip() == "esquema.json"
    assert f"esquema v{srv.VERSION_ESQUEMA}]" in srv.listar_proyectos()


def test_memoria_antigua_se_migra_en_la_primera_escritura(srv, proyecto):
    _quitar_esquema(proyecto["mem"])
    assert "registrada como propuesta" in srv.registrar_decision(proyecto="demo", titulo="A", decision="d", justificacion="j")
    assert _version(proyecto["mem"]) == srv.VERSION_ESQUEMA
    historial = log_git(proyecto["mem"])
    assert historial[1] == f"memoria: migrar esquema v0 → v{srv.VERSION_ESQUEMA}"   # migración en commit propio, antes
    assert historial[0].startswith("memoria: ADR-001")


def test_obtener_contexto_tambien_migra(srv, proyecto):
    _quitar_esquema(proyecto["mem"])
    assert not srv.obtener_contexto(proyecto="demo").startswith("ERROR")
    assert _version(proyecto["mem"]) == srv.VERSION_ESQUEMA


def test_cadena_de_migraciones_en_orden(srv, proyecto, monkeypatch):
    llamadas = []

    def a_v2(mem):
        llamadas.append(2)
        (mem / "nuevo.md").write_text("formato v2\n")
        return [mem / "nuevo.md"]

    def a_v3(mem):
        llamadas.append(3)
        return []
    monkeypatch.setattr(esquema, "VERSION_ESQUEMA", 3)
    monkeypatch.setattr(esquema, "MIGRACIONES", {**srv.MIGRACIONES, 2: a_v2, 3: a_v3})
    srv.registrar_pendiente(proyecto="demo", tema="T", contexto="c")
    assert llamadas == [2, 3] and _version(proyecto["mem"]) == 3
    assert log_git(proyecto["mem"])[1] == "memoria: migrar esquema v1 → v3"
    assert "nuevo.md" in subprocess.run(["git", "-C", str(proyecto["mem"]), "ls-files"],
                                        capture_output=True, text=True).stdout
    srv.registrar_pendiente(proyecto="demo", tema="T2", contexto="c")      # ya al día: no migra de nuevo
    assert llamadas == [2, 3]


def test_memoria_mas_nueva_que_el_servidor_no_se_toca(srv, proyecto):
    mem = proyecto["mem"]
    (mem / "esquema.json").write_text(json.dumps({"version": srv.VERSION_ESQUEMA + 1}))
    antes = log_git(mem)
    for salida in (srv.registrar_decision(proyecto="demo", titulo="A", decision="d", justificacion="j"),
                   srv.obtener_contexto(proyecto="demo")):
        assert salida.startswith("ERROR:") and "Actualiza memoria-proyectos" in salida
    assert log_git(mem) == antes and not list((mem / "decisiones").glob("ADR-*.md"))


def test_esquema_danado_es_rechazo_legible(srv, proyecto):
    (proyecto["mem"] / "esquema.json").write_text("{no es json")
    salida = srv.registrar_pendiente(proyecto="demo", tema="T", contexto="c")
    assert salida.startswith("ERROR:") and "dañado" in salida


def test_migracion_sin_commit_se_deshace(srv, proyecto, monkeypatch):
    """Hallazgo al migrar Fractall: si git no puede commitear, la migración no debe quedar a medias."""
    _quitar_esquema(proyecto["mem"])
    monkeypatch.setattr(esquema, "_commit", lambda *a, **k: "(git falló: Author identity unknown)")
    salida = srv.registrar_pendiente(proyecto="demo", tema="T", contexto="c")
    assert salida.startswith("ERROR:") and "Author identity unknown" in salida
    assert not (proyecto["mem"] / "esquema.json").exists()
    assert not list((proyecto["mem"] / "pendientes").glob("P-*.md"))
