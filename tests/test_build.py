"""T-016 (ADR-037): build id and fingerprint of the server, stale-server warning and in_progress block, routing with
build and time, report period by `at`, local source check and live processes in doctor, restart reminder."""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from test_upgrade import hogar  # noqa: F401  (fixture: temporary HOME for doctor)
from test_delegacion import _en_curso, _meta, _tarea

from ratifact import procesos

PAQUETE = Path(__file__).resolve().parents[1] / "ratifact"
SEPARADOR = "\n\n---\n\n"


@pytest.fixture
def copia(tmp_path) -> Path:
    """Temporary copy of the real package (with a __pycache__ to check that bytecode is ignored)."""
    destino = tmp_path / "pkg" / "ratifact"
    shutil.copytree(PAQUETE, destino, ignore=shutil.ignore_patterns("__pycache__"))
    (destino / "__pycache__").mkdir()
    (destino / "__pycache__" / "app.cpython-311.pyc").write_bytes(b"x")
    return destino


def _tocar(ruta: Path, texto: str = "\n# changed\n") -> None:
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(texto)
    st = ruta.stat()
    os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))     # mtime changes even on coarse clocks


# ───────────────────────── criteria 1–3: build and fingerprint ─────────────────────────

def test_build_tiene_version_y_siete_hex(copia):
    from ratifact import __version__, build
    v = build.Vigilante(copia)
    assert re.fullmatch(re.escape(__version__) + r"\+[0-9a-f]{7}", v.build)
    assert re.fullmatch(re.escape(__version__) + r"\+[0-9a-f]{7}", build.build_id())


def test_build_estable_y_cambia_con_el_contenido(copia):
    from ratifact import build
    assert build.build_de(copia) == build.build_de(copia)
    antes = build.build_de(copia)
    (copia / "__pycache__" / "otro.pyc").write_bytes(b"y")          # bytecode does not count
    assert build.build_de(copia) == antes
    _tocar(copia / "app.py")
    assert build.build_de(copia) != antes


def test_sin_cambios_no_esta_obsoleto(copia):
    from ratifact import build
    assert build.Vigilante(copia, ttl=0).obsoleto() is False


@pytest.mark.parametrize("cambio", ["modificar", "agregar", "borrar", "skill"])
def test_cambios_en_el_paquete_lo_vuelven_obsoleto(copia, cambio):
    from ratifact import build
    v = build.Vigilante(copia, ttl=0)
    if cambio == "modificar":
        _tocar(copia / "app.py")
    elif cambio == "agregar":
        (copia / "nuevo.py").write_text("x = 1\n")
    elif cambio == "borrar":
        (copia / "vocabulario.py").unlink()
    else:
        _tocar(next((copia / "skills").rglob("SKILL.md")))
    assert v.obsoleto() is True


def test_cambios_solo_en_pycache_no_cuentan(copia):
    from ratifact import build
    v = build.Vigilante(copia, ttl=0)
    (copia / "__pycache__" / "app.cpython-311.pyc").write_bytes(b"otro")
    (copia / "__pycache__" / "nuevo.cpython-311.pyc").write_bytes(b"z")
    (copia / "suelto.pyc").write_bytes(b"z")
    assert v.obsoleto() is False


def test_directorio_eliminado_esta_obsoleto(copia):
    from ratifact import build
    v = build.Vigilante(copia, ttl=0)
    shutil.rmtree(copia)
    assert v.obsoleto() is True


# ───────────────────────── review 1, criteria 16–17: content confirmation ─────────────────────────

def _reescribir_igual(raiz: Path) -> None:
    """What `uv tool install --reinstall` does without code changes: same bytes, new mtimes."""
    for p in raiz.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            datos = p.read_bytes()
            p.write_bytes(datos)
            st = p.stat()
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def _contar_hashes(monkeypatch) -> list:
    from ratifact import build
    llamadas, original = [], build.hash_contenido
    monkeypatch.setattr(build, "hash_contenido", lambda raiz: llamadas.append(raiz) or original(raiz))
    return llamadas


def test_reinstalar_con_el_mismo_contenido_no_es_obsoleto(copia, monkeypatch):
    from ratifact import build
    ahora = [0.0]
    v = build.Vigilante(copia, reloj=lambda: ahora[0], ttl=5)
    hashes = _contar_hashes(monkeypatch)
    _reescribir_igual(copia)
    assert v.obsoleto() is False and len(hashes) == 1          # new fingerprint → one content hash
    ahora[0] += 6                                              # cache expired
    assert v.obsoleto() is False and len(hashes) == 1          # the new fingerprint is the reference: stat only


def test_mtime_nuevo_y_contenido_distinto_es_obsoleto(copia, monkeypatch):
    from ratifact import build
    ahora = [0.0]
    v = build.Vigilante(copia, reloj=lambda: ahora[0], ttl=5)
    hashes = _contar_hashes(monkeypatch)
    _reescribir_igual(copia)
    (copia / "app.py").write_text((copia / "app.py").read_text() + "\n# otro\n")
    assert v.obsoleto() is True and len(hashes) == 1
    ahora[0] += 6
    assert v.obsoleto() is True and len(hashes) == 1           # same fingerprint seen: not hashed again


def test_borrar_y_recrear_con_el_mismo_contenido_no_es_obsoleto(copia, tmp_path):
    from ratifact import build
    v = build.Vigilante(copia, ttl=0)
    respaldo = tmp_path / "respaldo"
    shutil.copytree(copia, respaldo)
    shutil.rmtree(copia)
    assert v.obsoleto() is True                                # gone (criterion 2 unchanged)
    shutil.copytree(respaldo, copia)
    assert v.obsoleto() is False


def test_costo_de_la_verificacion_sin_cache():
    from ratifact import build
    v = build.Vigilante(PAQUETE, ttl=0)
    v.obsoleto()                                    # warm the OS cache, as in a long-running server
    inicio = time.perf_counter()
    v.obsoleto()
    assert (time.perf_counter() - inicio) * 1000 < 20


def test_con_cache_no_vuelve_a_tocar_el_disco(copia, monkeypatch):
    from ratifact import build
    ahora = [100.0]
    v = build.Vigilante(copia, reloj=lambda: ahora[0], ttl=5)
    llamadas = []
    original = build.huella
    monkeypatch.setattr(build, "huella", lambda raiz: llamadas.append(raiz) or original(raiz))
    assert v.obsoleto() is False and len(llamadas) == 1
    _tocar(copia / "app.py")
    ahora[0] += 4.9
    assert v.obsoleto() is False and len(llamadas) == 1        # still cached: no stat
    ahora[0] += 0.2
    assert v.obsoleto() is True and len(llamadas) == 2


# ───────────────────────── criteria 4–6: warning and in_progress block ─────────────────────────

def _obsoleto(monkeypatch, valor: bool) -> None:
    from ratifact import build
    monkeypatch.setattr(build, "obsoleto", lambda: valor)


def test_get_context_primera_linea_es_el_build(srv, proyecto, monkeypatch):
    from ratifact import build
    _obsoleto(monkeypatch, False)
    salida = srv.get_context(project="demo")
    assert salida.split("\n")[0] == f"ratifact {build.build_id()}"
    assert "⚠ This ratifact server" not in salida
    assert salida.split("\n\n", 1)[1].startswith("(INDEX.md does not exist)") or SEPARADOR in salida


def test_get_context_resto_sin_cambios(srv, proyecto, monkeypatch):
    _obsoleto(monkeypatch, False)
    normal = srv.get_context(project="demo").split("\n\n", 1)[1]
    _obsoleto(monkeypatch, True)
    salida = srv.get_context(project="demo")
    lineas = salida.split("\n")
    assert lineas[0].startswith("ratifact ")
    assert lineas[1].startswith("⚠ This ratifact server") and "Restart this client" in lineas[1]
    assert salida.split("\n\n", 1)[1] == normal


def test_in_progress_obsoleto_se_rechaza_sin_cambios(srv, proyecto, monkeypatch):
    from ratifact import build
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    archivo = _tarea(proyecto["mem"])
    antes = archivo.read_bytes()
    commits = subprocess.run(["git", "-C", str(proyecto["mem"]), "rev-list", "--count", "HEAD"],
                             capture_output=True, text=True).stdout
    _obsoleto(monkeypatch, True)
    salida = srv.update_task(project="demo", id="T-001", status="in_progress")
    assert salida.startswith("ERROR") and f"ratifact {build.build_id()}" in salida
    assert "Restart this client" in salida and "in_progress" in salida
    assert archivo.read_bytes() == antes
    assert subprocess.run(["git", "-C", str(proyecto["mem"]), "rev-list", "--count", "HEAD"],
                          capture_output=True, text=True).stdout == commits
    assert subprocess.run(["git", "-C", str(proyecto["mem"]), "status", "--porcelain"],
                          capture_output=True, text=True).stdout == ""
    assert _meta(proyecto["mem"])["status"] == "todo"


def test_las_demas_herramientas_funcionan_con_el_aviso(srv, proyecto, monkeypatch):
    _en_curso(srv)
    _obsoleto(monkeypatch, True)
    for salida in (srv.update_task(project="demo", id="T-001", status="in_review", result="Workers: none — "
                                                                                          "reason: prueba"),
                   srv.search(project="demo", query="Algo"),
                   srv.read_task(project="demo", id="T-001"),
                   srv.update_task(project="demo", id="T-001", status="merged")):
        assert salida.startswith("⚠ This ratifact server"), salida
        assert "ERROR" not in salida.split("\n\n", 1)[1][:6]
    assert _meta(proyecto["mem"])["status"] == "merged"


def test_sin_obsolescencia_ninguna_respuesta_lleva_el_aviso(srv, proyecto, monkeypatch):
    _obsoleto(monkeypatch, False)
    salidas = [_en_curso(srv), srv.search(project="demo", query="Algo"), srv.read_task(project="demo", id="T-001"),
               srv.update_task(project="demo", id="T-001", status="in_review", result="x"),
               srv.get_context(project="demo")]
    assert not any("⚠ This ratifact server" in s for s in salidas)


def test_extremo_a_extremo_con_obsolescencia_real(srv, proyecto, copia, monkeypatch):
    """Criterion 18: the real check (not forced) on a copy of the package that is rewritten in place."""
    from ratifact import build
    monkeypatch.setattr(build, "_VIGILANTE", build.Vigilante(copia, ttl=0))
    srv.create_task(project="demo", title="Uno", goal="o", acceptance_criteria="c")
    srv.create_task(project="demo", title="Dos", goal="o", acceptance_criteria="c")
    _reescribir_igual(copia)
    salida = srv.update_task(project="demo", id="T-001", status="in_progress")
    assert salida.startswith("T-001 → in_progress") and "⚠ This ratifact server" not in salida
    assert "⚠ This ratifact server" not in srv.get_context(project="demo")
    (copia / "app.py").write_text((copia / "app.py").read_text() + "\n# otro\n")
    salida = srv.update_task(project="demo", id="T-002", status="in_progress")
    assert salida.startswith(build.MARCA_ERROR_OBSOLETO) and _meta(proyecto["mem"], "T-002")["status"] == "todo"
    assert srv.get_context(project="demo").split("\n")[1].startswith("⚠ This ratifact server")


# ───────────────────────── criteria 7–8: routing and report ─────────────────────────

def test_routing_graba_build_y_fecha(srv, proyecto):
    from ratifact import build
    _en_curso(srv)
    routing = _meta(proyecto["mem"])["routing"]
    m = re.fullmatch(r"explore=\S+,write=\S+,verify=\S+ · delegation=required · build=(\S+) · at=(\S+)", routing)
    assert m, routing
    assert m.group(1) == build.build_id()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d[+-]\d\d:\d\d", m.group(2)), m.group(2)


def test_lectores_aceptan_ambos_formatos():
    from ratifact.delegacion import at_de_routing, build_de_routing, politica_de_routing
    viejo = "explore=haiku,write=sonnet,verify=sonnet · delegation=required"
    nuevo = viejo + " · build=1.0.0+abc1234 · at=2026-10-25T18:40-06:00"
    assert politica_de_routing(viejo) == politica_de_routing(nuevo) == "required"
    assert build_de_routing(viejo) is None and at_de_routing(viejo) is None
    assert build_de_routing(nuevo) == "1.0.0+abc1234"
    assert at_de_routing(nuevo) == dt.datetime(2026, 10, 25, 18, 40, tzinfo=dt.timezone(dt.timedelta(hours=-6)))


def test_aviso_in_review_con_ambos_formatos(srv, proyecto):
    from ratifact.registros import _escribir_registro, _leer_registro
    _en_curso(srv)
    assert "Delegation was required" in srv.update_task(project="demo", id="T-001", status="in_review", result="x")
    archivo = _tarea(proyecto["mem"])
    meta, cuerpo = _leer_registro(archivo)
    meta["routing"], meta["status"] = "explore=session,write=session,verify=session · delegation=required", "in_progress"
    _escribir_registro(archivo, meta, cuerpo)
    assert "Delegation was required" in srv.update_task(project="demo", id="T-001", status="in_review", result="y")


def test_report_usa_at_y_updated_solo_sin_at(srv, proyecto):
    from ratifact.informe_memoria import indicador_delegacion
    from ratifact.registros import _escribir_registro, _leer_registro
    hoy = dt.date.today()
    viejo, reciente = (hoy - dt.timedelta(days=30)).isoformat(), hoy.isoformat()
    base = "explore=session,write=session,verify=session · delegation=required"
    casos = {"T-001": (f"{base} · build=1.0.0+abc1234 · at={viejo}T10:00-06:00", reciente),    # at old → out
             "T-002": (f"{base} · build=1.0.0+abc1234 · at={reciente}T10:00-06:00", viejo),    # at recent → in
             "T-003": (base, reciente),                                                         # no at, updated → in
             "T-004": (base, viejo)}                                                            # no at, old → out
    for id_, (routing, updated) in casos.items():
        _en_curso(srv, id_)
        archivo = _tarea(proyecto["mem"], id_)
        meta, cuerpo = _leer_registro(archivo)
        meta["routing"], meta["updated"] = routing, updated
        _escribir_registro(archivo, meta, cuerpo)
    lineas = indicador_delegacion(dt.datetime.now() - dt.timedelta(days=7), "demo")
    assert lineas[0].startswith("  demo: 2 tareas con routing · required 2 "), lineas[0]


# ───────────────────────── criteria 9–10: local source ─────────────────────────

def _recibo(tmp_path: Path, requisito: str) -> Path:
    ruta = tmp_path / "uv-receipt.toml"
    ruta.write_text(f'[tool]\nrequirements = [{requisito}]\n', encoding="utf-8")
    return ruta


def test_fuente_local_desde_el_recibo(tmp_path):
    from ratifact import build
    local = _recibo(tmp_path, '{ name = "ratifact", directory = "/home/u/src/ratifact" }')
    assert build.fuente_local(PAQUETE, local) == Path("/home/u/src/ratifact")


def test_fuente_pypi_ausente_o_ilegible_no_es_local(tmp_path):
    from ratifact import build
    assert build.fuente_local(PAQUETE, _recibo(tmp_path, '{ name = "ratifact" }')) is None
    assert build.fuente_local(PAQUETE, _recibo(tmp_path, '{ name = "ratifact", git = "https://x/r.git" }')) is None
    assert build.fuente_local(tmp_path / "sin-recibo" / "ratifact") is None
    roto = tmp_path / "roto.toml"
    roto.write_text("[tool\nrequirements = ", encoding="utf-8")
    assert build.fuente_local(PAQUETE, roto) is None
    binario = tmp_path / "bin.toml"
    binario.write_bytes(b"\xff\xfe\x00")
    assert build.fuente_local(PAQUETE, binario) is None


@pytest.fixture
def instalacion(tmp_path):
    """Fake uv tool layout: <tool>/lib/python3.11/site-packages/ratifact with its receipt, and a local source."""
    fuente = tmp_path / "src"
    shutil.copytree(PAQUETE, fuente / "ratifact", ignore=shutil.ignore_patterns("__pycache__"))
    herramienta = tmp_path / "tool"
    paquete = herramienta / "lib" / "python3.11" / "site-packages" / "ratifact"
    shutil.copytree(PAQUETE, paquete, ignore=shutil.ignore_patterns("__pycache__"))
    (herramienta / "uv-receipt.toml").write_text(
        f'[tool]\nrequirements = [{{ name = "ratifact", directory = "{fuente}" }}]\n', encoding="utf-8")
    return {"fuente": fuente, "paquete": paquete}


def test_doctor_fuente_igual_distinta_e_inexistente(hogar, instalacion):
    from ratifact import doctor
    lineas, acciones = doctor.informe(procesos=lambda: [], paquete=instalacion["paquete"], vivos=lambda: [])
    assert f"Source: {instalacion['fuente']} · same as the installation" in lineas
    assert not any("source newer" in a for a in acciones)
    _tocar(instalacion["fuente"] / "ratifact" / "app.py")
    lineas, acciones = doctor.informe(procesos=lambda: [], paquete=instalacion["paquete"], vivos=lambda: [])
    assert any("source newer than the installation: reinstall" in l for l in lineas)
    assert any(f"uv tool install --reinstall {instalacion['fuente']}" in a for a in acciones), acciones
    shutil.rmtree(instalacion["fuente"])
    lineas, acciones = doctor.informe(procesos=lambda: [], paquete=instalacion["paquete"], vivos=lambda: [])
    assert any("NOT FOUND" in l for l in lineas)
    assert any("was not found" in a for a in acciones)


def test_get_context_avisa_fuente_distinta_y_calla_si_no_existe(srv, proyecto, monkeypatch, instalacion):
    from ratifact import build
    monkeypatch.setattr(build, "PAQUETE", instalacion["paquete"])
    _obsoleto(monkeypatch, False)
    assert "is newer than the installation" not in srv.get_context(project="demo")
    _tocar(instalacion["fuente"] / "ratifact" / "app.py")
    lineas = srv.get_context(project="demo").split("\n")
    assert lineas[0].startswith("ratifact ") and lineas[1].startswith("⚠ The ratifact source")
    assert f"uv tool install --reinstall {instalacion['fuente']}" in lineas[1]
    shutil.rmtree(instalacion["fuente"])
    assert "⚠ The ratifact source" not in srv.get_context(project="demo")


# ───────────────────────── criterion 11: live processes ─────────────────────────

def _ps(*filas: str) -> str:
    return "\n".join(filas) + "\n"


INSTALACION = dt.datetime(2026, 10, 25, 17, 51, 31)
PS = _ps("  100     1 Sat Oct 24 18:53:54 2026 /opt/claude-code/bin/claude --resume x",
         "  101   100 Sat Oct 24 18:53:54 2026 /tool/bin/python3 /home/u/.local/bin/ratifact serve",
         "  102   100 Sat Oct 24 19:00:00 2026 /tool/bin/python3 /home/u/.local/bin/ratifact serve",
         "  103   100 Sat Oct 24 19:10:00 2026 /tool/bin/python3 -m ratifact.cli serve",
         "  104   100 Sat Oct 24 19:20:00 2026 /tool/bin/python3 /home/u/.local/bin/ratifact serve",
         "  200     1 Sun Oct 25 17:53:00 2026 /usr/bin/claude-desktop",
         "  201   200 Sun Oct 25 17:53:31 2026 /tool/bin/python3 /home/u/.local/bin/ratifact serve",
         "  300     1 Sun Oct 25 17:00:00 2026 nvim ratifact/servidor.py serve-notes")


def _instalada_a(raiz: Path, cuando: dt.datetime) -> None:
    for p in raiz.rglob("*"):
        if p.is_file():
            os.utime(p, (cuando.timestamp(),) * 2)


def _registro(carpeta: Path, pid: int, inicio: str, contenido: str) -> None:
    import json
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pid}.json").write_text(json.dumps({"pid": pid, "build": f"1.0.0+{contenido[:7]}",
                                                     "content": contenido, "started": inicio}))


def test_procesos_anteriores_solo_si_el_contenido_difiere(tmp_path, copia):
    """Criterion 19: started before the installation → stale only with a record of different content; same content →
    nothing to do; no record or a reused PID → unknown; started after → not flagged."""
    from ratifact import build
    _instalada_a(copia, INSTALACION)
    registros = tmp_path / "servers"
    _registro(registros, 101, "2026-10-24T18:53:54", "f" * 64)                        # different content
    _registro(registros, 102, "2026-10-24T19:00:01", build.hash_contenido(copia))      # same content
    _registro(registros, 104, "2026-10-20T08:00:00", "f" * 64)                         # reused PID: start differs
    vivos = procesos.procesos_vivos(copia, correr=lambda: PS, registros=registros)
    assert [(p.pid, p.padre, p.estado, p.anterior) for p in vivos] == [
        (101, "claude", "stale", True), (102, "claude", "same", False), (103, "claude", "unknown", False),
        (104, "claude", "unknown", False), (201, "claude-desktop", "after", False)]
    assert vivos[0].inicio == dt.datetime(2026, 10, 24, 18, 53, 54) and vivos[0].build == "1.0.0+fffffff"


def test_doctor_muestra_los_tres_casos_ninguno_y_error(hogar, copia):
    from ratifact import doctor
    inicio = dt.datetime(2026, 10, 24, 18, 53, 54)
    vivos = [procesos.ProcesoVivo(101, inicio, "claude", True, procesos.ANTERIOR, "1.0.0+fffffff"),
             procesos.ProcesoVivo(102, inicio, "claude", False, procesos.MISMO, "1.0.0+abc1234"),
             procesos.ProcesoVivo(103, inicio, "claude", False, procesos.DESCONOCIDO),
             procesos.ProcesoVivo(201, inicio, "claude-desktop")]
    lineas, acciones = doctor.informe(procesos=lambda: [], paquete=copia, vivos=lambda: vivos)
    texto = "\n".join(lineas)
    assert ("PID 101 · started 2026-10-24 18:53:54 · parent claude ⚠ started BEFORE the installation and runs "
            "different content (ratifact 1.0.0+fffffff): restart its client") in texto
    assert "PID 102 · started 2026-10-24 18:53:54 · parent claude · started before the reinstallation, same content " \
           "(ratifact 1.0.0+abc1234): nothing to do" in texto
    linea = next(l for l in lineas if "PID 103" in l)
    assert "the content may be identical" in linea and "get_context in that client gives the definitive answer" in linea
    assert "⚠" not in linea
    assert next(l for l in lineas if "PID 201" in l).endswith("parent claude-desktop")
    lineas, _ = doctor.informe(procesos=lambda: [], paquete=copia, vivos=lambda: [])
    assert any(l.startswith("Running `ratifact serve` processes: none") for l in lineas)

    def falla():
        raise OSError("ps not found")
    lineas, _ = doctor.informe(procesos=lambda: [], paquete=copia, vivos=falla)
    assert "Running `ratifact serve` processes: cannot be listed (ps not found)" in lineas


def test_registro_se_escribe_limpia_muertos_y_se_borra(tmp_path, copia):
    import json
    from ratifact import build
    carpeta = tmp_path / "servers"
    _registro(carpeta, 999_999_999, "2026-10-24T18:53:54", "f" * 64)                 # a PID that does not exist
    v = build.Vigilante(copia)
    ruta = procesos.registrar(v, carpeta)
    datos = json.loads(ruta.read_text())
    assert ruta.name == f"{os.getpid()}.json" and datos["build"] == v.build and datos["content"] == v.contenido
    assert not (carpeta / "999999999.json").exists()
    inicio = dt.datetime.fromisoformat(datos["started"])
    assert procesos.leer_registro(os.getpid(), inicio, carpeta)["content"] == v.contenido
    assert procesos.leer_registro(os.getpid(), inicio + dt.timedelta(minutes=1), carpeta) is None
    procesos.desregistrar(ruta)
    assert not ruta.exists()


def test_limpieza_no_envia_senales(tmp_path, copia, monkeypatch):
    """Review finding R4-win-kill-terminates: pruning never calls os.kill where it would terminate the process."""
    from ratifact import build
    llamadas = []
    monkeypatch.setattr(procesos.os, "kill", lambda *a: llamadas.append(a))
    carpeta, vigilante = tmp_path / "servers", build.Vigilante(copia)
    _registro(carpeta, 999_999_999, "2026-10-24T18:53:54", "f" * 64)
    procesos.registrar(vigilante, carpeta)
    if Path("/proc/self").is_dir():
        assert llamadas == [] and not (carpeta / "999999999.json").exists()      # Linux: /proc, no signal
    else:
        assert all(a[1] == 0 for a in llamadas)                                   # other POSIX: signal 0 only
    llamadas.clear()
    monkeypatch.setattr(procesos, "Path", lambda *a: tmp_path / "sin-proc" if a == ("/proc/self",) else Path(*a))
    monkeypatch.setattr(procesos.os, "name", "nt")
    _registro(carpeta, 999_999_998, "2026-10-24T18:53:54", "f" * 64)
    procesos.registrar(vigilante, carpeta)
    assert llamadas == [] and (carpeta / "999999998.json").exists()              # Windows: nothing probed, kept


def test_registro_que_no_se_puede_escribir_no_rompe(tmp_path, copia):
    from ratifact import build
    archivo = tmp_path / "ocupado"
    archivo.write_text("x")                                     # a file where the folder should be
    assert procesos.registrar(build.Vigilante(copia), archivo / "servers") is None
    assert procesos.leer_registro(1, dt.datetime.now(), archivo / "servers") is None


def test_serve_registra_el_servidor_y_lo_borra_al_salir(hogar, monkeypatch):
    import atexit
    from ratifact import cli
    salidas = []
    monkeypatch.setattr(atexit, "register", lambda fn, *a: salidas.append((fn, a)))
    vistos = []

    class Falso:
        def run(self):
            vistos.append(sorted(p.name for p in procesos.carpeta_registro().glob("*.json")))
    monkeypatch.setattr(cli, "servidor", lambda: Falso())
    cli.main(["serve"])
    assert vistos == [[f"{os.getpid()}.json"]]                  # written before serving
    fn, args = salidas[-1]
    fn(*args)
    assert not list(procesos.carpeta_registro().glob("*.json"))     # removed on exit


def test_listado_real_solo_lectura_no_falla():
    try:
        vivos = procesos.procesos_vivos(PAQUETE)
    except OSError:
        pytest.skip("ps is not available")
    assert all(p.pid != os.getpid() for p in vivos)


# ───────────────────────── criterion 12: restart reminder ─────────────────────────

def test_recordatorio_dice_reiniciar_y_verificar():
    from ratifact import build
    assert "Restart the clients" in build.RECORDATORIO and "ratifact doctor" in build.RECORDATORIO
    # install --apply and upgrade --apply print it: tests/test_install.py and tests/test_upgrade.py check their output


def test_docs_documentan_el_procedimiento():
    raiz = PAQUETE.parent
    for doc in ("README.md", "LEEME.md", "docs/publish.md"):
        texto = (raiz / doc).read_text(encoding="utf-8")
        assert "uv tool install --reinstall" in texto and "ratifact doctor" in texto, doc
    assert "build=" in (raiz / "docs" / "optional-integrations.md").read_text(encoding="utf-8")
