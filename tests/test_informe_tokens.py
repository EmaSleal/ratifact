"""`ratifact report` token usage section (transcripts of Claude Code): synthetic JSONL in a temp CLAUDE_CONFIG_DIR."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from test_delegacion import _settings, _tarea
from test_informe_delegacion import _salida_report

UTC = dt.timezone.utc
T0 = (dt.datetime.now(UTC) - dt.timedelta(days=2)).replace(microsecond=0)
OK = "Workers: write/sonnet×1, verify/sonnet×1"
NADA = "Workers: none — reason: tiny"
CABECERA = "Token usage (Claude Code transcripts)"


@pytest.fixture
def claude(entorno, monkeypatch):
    """CLAUDE_CONFIG_DIR temporal: ninguna prueba lee el ~/.claude real."""
    base = entorno["tmp"] / "claude"
    (base / "projects" / "demo").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(base))
    monkeypatch.setenv("HOME", str(entorno["tmp"] / "home"))
    return base / "projects" / "demo"


def _en(minutos: float) -> dt.datetime:
    return T0 + dt.timedelta(minutes=minutos)


def _ejecutar(srv, monkeypatch, id_: str, ini: float, fin: float, resultado: str = OK, crear: bool = True,
              delegation: str = "") -> None:
    """Task run with controlled commit times (the windows come from the memory's git history)."""
    if crear:
        srv.create_task(project="demo", title=f"Algo {id_}", goal="o", acceptance_criteria="c", delegation=delegation)
    monkeypatch.setenv("GIT_COMMITTER_DATE", _en(ini).isoformat())
    assert srv.update_task(project="demo", id=id_, status="in_progress").startswith(f"{id_} → in_progress")
    monkeypatch.setenv("GIT_COMMITTER_DATE", _en(fin).isoformat())
    assert not srv.update_task(project="demo", id=id_, status="in_review", result=resultado).startswith("ERROR")


def _rama(proyecto, id_: str) -> str:
    from test_delegacion import _meta
    return _meta(proyecto["mem"], id_)["branch"]


def _l(min_: float, cwd, rama: str, modelo: str = "claude-opus", mid: str | None = "m1", rid: str | None = "r1",
       sal: int = 10, ent: int = 1, cw: int = 0, cr: int = 0, lado: bool = False, agente: str | None = None) -> dict:
    d = {"timestamp": _en(min_).strftime("%Y-%m-%dT%H:%M:%S.123Z"), "cwd": str(cwd), "gitBranch": rama,
         "isSidechain": lado, "requestId": rid,
         "message": {"id": mid, "model": modelo, "role": "assistant", "content": "SECRETO",
                     "usage": {"input_tokens": ent, "output_tokens": sal, "cache_creation_input_tokens": cw,
                               "cache_read_input_tokens": cr, "service_tier": "standard", "cache_creation": {"x": 1}}}}
    if agente:
        d["agentId"] = agente
    return d


def _a(min_: float, cwd, rama: str = "main") -> dict:
    """Line without usage: only activity (anchors a session near a transition)."""
    return {"timestamp": _en(min_).strftime("%Y-%m-%dT%H:%M:%S.123Z"), "cwd": str(cwd), "gitBranch": rama}


def _escribir(ruta: Path, lineas: list) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("".join((l if isinstance(l, str) else json.dumps(l)) + "\n" for l in lineas), encoding="utf-8")
    return ruta


def _activar(entorno, valor="on"):
    _settings(entorno, {"token_usage": valor})


def _informe(entorno, capsys, dias=14) -> str:
    salida = _salida_report(entorno, capsys, [{"herramienta": "get_context", "resp_chars": 10, "error": False,
                                                "ts": dt.datetime.now().isoformat(timespec="seconds"), "proyecto": "demo"}],
                            dias=dias)
    return salida[salida.index(CABECERA):] if CABECERA in salida else ""


def _seccion(entorno, capsys) -> str:
    return _informe(entorno, capsys).split("\nOpen pending")[0]


# ───────────────────────── criterios 1, 2, 3: activación ─────────────────────────

def test_off_no_abre_transcripciones(srv, proyecto, entorno, claude, monkeypatch, capsys):
    from ratifact import informe_tokens
    _ejecutar(srv, monkeypatch, "T-001", 0, 10)

    def no(*a, **k):
        raise AssertionError("transcripts must not be read")
    monkeypatch.setattr(informe_tokens, "cargar_sesiones", no)
    monkeypatch.setattr(informe_tokens, "seccion", no)
    for ajuste in (None, "off", "sometimes", 5):       # absent, off, invalid: all treated as off
        if ajuste is not None:
            _activar(entorno, ajuste)
        salida = _salida_report(entorno, capsys, [{"herramienta": "get_context", "resp_chars": 10, "error": False,
                                                    "ts": dt.datetime.now().isoformat(timespec="seconds")}])
        assert CABECERA not in salida and "Delegation:" in salida


def test_valor_invalido_es_off_y_doctor_lo_informa(srv, proyecto, entorno, hogar_doctor):
    from ratifact import doctor, modelos
    _activar(entorno, "always")
    assert modelos.token_usage(modelos.ruta_settings(Path(os.environ["MEMORIA_PROYECTOS_CONFIG"]))) == "off"
    lineas, acciones = doctor.informe(procesos=lambda: [])
    assert any("invalid `token_usage` 'always'" in a for a in acciones)
    assert not any("token_usage: " in l for l in lineas if l.startswith("Settings:"))
    _settings(entorno, {"delegation": "x", "token_usage": "y"})     # one invalid key does not hide the other
    acciones = doctor.informe(procesos=lambda: [])[1]
    assert any("invalid `delegation`" in a for a in acciones) and any("invalid `token_usage`" in a for a in acciones)


def test_doctor_muestra_token_usage_efectivo(srv, proyecto, entorno, hogar_doctor):
    from ratifact import doctor
    texto = "\n".join(doctor.informe(procesos=lambda: [])[0])
    assert "token_usage: off (default)" in texto
    _settings(entorno, {"models": {"write": "sonnet"}})
    assert "global models: write=sonnet · delegation: required (default) · token_usage: off (default)" in \
        "\n".join(doctor.informe(procesos=lambda: [])[0])
    _activar(entorno)
    assert "· token_usage: on" in "\n".join(doctor.informe(procesos=lambda: [])[0])


@pytest.fixture
def hogar_doctor(entorno, monkeypatch):
    home = entorno["tmp"] / "home"
    home.mkdir(exist_ok=True)
    for k, v in {"HOME": home, "XDG_STATE_HOME": home / ".local" / "state", "XDG_CONFIG_HOME": home / ".config"}.items():
        monkeypatch.setenv(k, str(v))


# ───────────────────────── criterio 4: directorio base ─────────────────────────

def test_sin_directorio_de_transcripciones(srv, proyecto, entorno, claude, monkeypatch, capsys):
    import shutil
    _ejecutar(srv, monkeypatch, "T-001", 0, 10)
    _activar(entorno)
    shutil.rmtree(claude.parent)
    salida = _seccion(entorno, capsys)
    assert "no transcripts found" in salida and str(claude.parent) in salida


def test_directorio_por_defecto_es_home(entorno, monkeypatch):
    from ratifact import informe_tokens
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(entorno["tmp"] / "h"))
    assert informe_tokens.directorio_base() == Path(entorno["tmp"] / "h" / ".claude" / "projects")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(entorno["tmp"] / "c"))
    assert informe_tokens.directorio_base() == entorno["tmp"] / "c" / "projects"


# ───────────────────────── criterios 5, 6: lectura y deduplicación ─────────────────────────

def test_lineas_basura_se_ignoran(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 0, 60)
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    malo = _l(5, cwd, rama, mid="x1")
    malo["message"]["usage"]["output_tokens"] = "10"          # wrong type: that field counts as 0
    sin_uso = _l(6, cwd, rama, mid="x2")
    del sin_uso["message"]["usage"]
    _escribir(claude / "s1.jsonl", [
        "no es json", "[1, 2]", "{}", '{"message": 3}', "", _l(1, cwd, rama, mid="a", sal=7, ent=2, cw=3, cr=4),
        malo, sin_uso, {**_l(7, cwd, rama, mid="b"), "timestamp": "nunca"},
        {**_l(8, cwd, rama, mid="c"), "message": {"id": "c", "model": "m", "usage": "x"}},
        _l(9, cwd, rama, mid="d", modelo="<synthetic>", sal=500)])
    _activar(entorno)
    salida = _seccion(entorno, capsys)
    assert "main session: claude-opus: in 3 · out 7 · cache write 3 · cache read 4" in salida, salida
    assert "SECRETO" not in salida


def test_mensaje_repetido_suma_el_maximo(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 0, 60)
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    _escribir(claude / "s1.jsonl", [_l(1, cwd, rama, sal=1), _l(2, cwd, rama, sal=5, cr=9), _l(3, cwd, rama, sal=5)])
    _activar(entorno)
    assert "claude-opus: in 1 · out 5 · cache write 0 · cache read 9" in _seccion(entorno, capsys)


def test_archivos_viejos_se_descartan_por_mtime(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 0, 60)
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    ruta = _escribir(claude / "s1.jsonl", [_l(1, cwd, rama, sal=5)])
    viejo = (dt.datetime.now() - dt.timedelta(days=30)).timestamp()
    os.utime(ruta, (viejo, viejo))
    _activar(entorno)
    assert "T-001 · delegation=required: no data" in _seccion(entorno, capsys)


# ───────────────────────── criterio 7: atribución ─────────────────────────

def test_atribucion_a_b_c(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 10, 60)
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    otro = entorno["tmp"] / "otro-proyecto"
    _escribir(claude / "dentro.jsonl", [
        _a(10, cwd, "main"),                              # anchor at the window start (no usage)
        _l(0, cwd, "main", mid="antes", sal=1000),        # (b-like) before the window, on main
        _l(20, cwd / "sub", "main", mid="a", sal=20),     # (a) main, inside the window, session also has the branch; cwd below the project
        _l(30, cwd, rama, mid="b", sal=30),
        _l(90, cwd, rama, mid="fuera", sal=2000),         # (b) on the branch but after the window
    ])
    _escribir(claude / "ajena.jsonl", [_a(10, otro, rama), _l(20, otro, rama, mid="c", sal=4000)])   # (c) another cwd, anchored
    _escribir(claude / "sinanclaje.jsonl", [_l(20, cwd, "main", mid="d", sal=8000)])  # in the project but no line near a transition
    _activar(entorno)
    assert "main session: claude-opus: in 2 · out 50 · cache write 0 · cache read 0" in _seccion(entorno, capsys)


def test_dos_ejecuciones_suman_ambas_ventanas(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 10, 20)
    monkeypatch.setenv("GIT_COMMITTER_DATE", _en(25).isoformat())
    srv.update_task(project="demo", id="T-001", status="changes_requested")
    _ejecutar(srv, monkeypatch, "T-001", 40, 50, crear=False)
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, cwd, rama), _a(40, cwd, rama), _l(15, cwd, rama, mid="1", sal=1), _l(30, cwd, rama, mid="2", sal=100),
                                   _l(45, cwd, rama, mid="3", sal=10), _l(55, cwd, rama, mid="4", sal=1000)])
    _activar(entorno)
    assert "out 11 ·" in _seccion(entorno, capsys)


def test_ventana_sin_in_review_termina_ahora(srv, proyecto, entorno, claude, monkeypatch, capsys):
    srv.create_task(project="demo", title="Algo T-001", goal="o", acceptance_criteria="c")
    monkeypatch.setenv("GIT_COMMITTER_DATE", _en(10).isoformat())
    srv.update_task(project="demo", id="T-001", status="in_progress")
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, cwd, rama), _l(500, cwd, rama, sal=3)])
    _activar(entorno)
    assert "out 3 ·" in _seccion(entorno, capsys)


# ───────────────────────── criterio 8: un mensaje, una tarea ─────────────────────────

def test_solape_gana_la_rama_y_si_no_la_ventana_mas_reciente(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 10, 100)
    _ejecutar(srv, monkeypatch, "T-002", 50, 120)
    r1, r2, cwd = _rama(proyecto, "T-001"), _rama(proyecto, "T-002"), proyecto["repo"]
    _escribir(claude / "s.jsonl", [
        _a(10, cwd, r1), _a(50, cwd, r2),
        _l(20, cwd, r1, mid="solo1", sal=1),             # only T-001 window
        _l(60, cwd, r1, mid="rama1", sal=10),            # both windows, branch of T-001
        _l(70, cwd, r2, mid="rama2", sal=100),           # both windows, branch of T-002
        _l(80, cwd, "main", mid="nadie", sal=1000),      # both windows, no branch: latest started (T-002)
        _l(110, cwd, "main", mid="solo2", sal=10000),    # only T-002
    ])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    t1, t2 = s.split("    T-002")
    assert "out 11 ·" in t1 and "out 11,100 ·" in t2, s
    assert "out 1,010" not in s


# ───────────────────────── criterios 9, 10, 11: formato ─────────────────────────

def test_seccion_exacta(srv, proyecto, entorno, claude, monkeypatch, capsys):
    from ratifact.informe_tokens import NOTA
    _ejecutar(srv, monkeypatch, "T-001", 10, 100)                       # delegated, with data
    _ejecutar(srv, monkeypatch, "T-002", 110, 120)                      # delegated, no data
    _ejecutar(srv, monkeypatch, "T-003", 130, 140, resultado=NADA)      # not delegated, no data
    r, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    sub = claude / "s1" / "subagents"
    _escribir(claude / "s1.jsonl", [_a(10, cwd, r), _l(15, cwd, r, ent=1200, sal=3400, cw=500, cr=1234567),
                                    _l(16, cwd, r, modelo="claude-haiku", mid="m2", rid="r2", sal=1)])
    _escribir(sub / "agent-a1.jsonl", [_l(20, cwd, r, modelo="claude-sonnet", mid="w1", rid="q1", sal=2000, cr=10000,
                                           lado=True, agente="a1")])
    _escribir(sub / "agent-a2.jsonl", [_l(30, cwd, r, modelo="claude-haiku", mid="w2", rid="q2", sal=500, cr=2000,
                                           lado=True, agente="a2"),
                                       _l(31, cwd, r, modelo="claude-haiku", mid="w3", rid="q3", sal=500, cr=1000,
                                           lado=True, agente="a2")])
    _escribir(sub / "agent-a3.jsonl", [_l(5, cwd, r, mid="w9", rid="q9", sal=99999, lado=True, agente="a3")])  # outside
    _activar(entorno)
    salida = _seccion(entorno, capsys)
    assert salida == "\n".join([
        CABECERA,
        "  demo:",
        "    T-001 · delegation=required",
        "      main session: claude-haiku: in 1 · out 1 · cache write 0 · cache read 0; "
        "claude-opus: in 1,200 · out 3,400 · cache write 500 · cache read 1,234,567",
        "      workers: 2 workers — claude-haiku: in 2 · out 1,000 · cache write 0 · cache read 3,000; "
        "claude-sonnet: in 1 · out 2,000 · cache write 0 · cache read 10,000",
        "    T-002 · delegation=required: no data",
        "    T-003 · delegation=required: no data",
        "    delegated: 1 of 2 tasks with data · average per task — main session: out 3,401 · cache read 1,234,567; "
        "workers: out 3,000 · cache read 13,000",
        "      median per task — main session: out 3,401 · cache read 1,234,567; workers: out 3,000 · cache read 13,000",
        "    not delegated: —",
        NOTA, ""])


def test_promedios_y_singular(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 10, 20)
    _ejecutar(srv, monkeypatch, "T-002", 30, 40, resultado=NADA)
    _ejecutar(srv, monkeypatch, "T-003", 50, 60, resultado=NADA)
    cwd = proyecto["repo"]
    for n, (id_, minu, sal) in enumerate((("T-001", 15, 10), ("T-002", 35, 7), ("T-003", 55, 4))):
        r = _rama(proyecto, id_)
        _escribir(claude / f"s{n}.jsonl", [_a(minu - 5, cwd, r), _l(minu, cwd, r, mid=f"a{n}", sal=sal, cr=100 * (n + 1))])
    _escribir(claude / "s1" / "subagents" / "agent-x.jsonl",
              [_l(36, cwd, _rama(proyecto, "T-002"), mid="w", rid="q", sal=40, cr=2, lado=True, agente="x")])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    assert "    delegated: 1 of 1 task with data · average per task — main session: out 10 · cache read 100; workers: out 0 · cache read 0" in s
    assert "    not delegated: 2 of 2 tasks with data · average per task — main session: out 6 · cache read 250; " \
           "workers: out 20 · cache read 1" in s
    assert "workers: 1 worker — claude-opus" in s and "workers: 0 workers — none" in s
    for malo in ("1 workers", "1 tasks"):
        assert malo not in s
