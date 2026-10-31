"""T-020 (P-027): doctor cuenta como servidor solo el proceso con registro por PID (ADR-038) y muestra el envoltorio
(Claude Desktop en Linux) agrupado bajo su servidor. Árbol de procesos y carpeta de registros simulados."""
import json
from pathlib import Path

import pytest

from test_upgrade import hogar, vieja  # noqa: F401,F811  (fixtures)

from ratifact import doctor, procesos
from ratifact.instalacion import Proceso

CMD = "/tool/bin/python3 /home/u/.local/bin/ratifact serve"


def _ps(*filas: str) -> str:
    return "\n".join(filas) + "\n"


def _fila(pid: int, ppid: int, hora: str, comando: str) -> str:
    return f"  {pid} {ppid} Sat Oct 31 {hora} 2026 {comando}"


def _registrar(carpeta: Path, pid: int, hora: str) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{pid}.json").write_text(json.dumps({"pid": pid, "build": "1.0.0+abc1234", "content": "a" * 64,
                                                     "started": f"2026-10-31T{hora}"}))


# P-027: two wrapper -> server pairs (Claude Desktop on Linux), plus a Claude Code server with no wrapper.
P027 = _ps(_fila(1000, 1, "09:00:00", "/usr/lib/claude-desktop/claude-desktop"),
           _fila(229497, 1000, "10:00:00", f"/usr/lib/claude-desktop/disclaimer {CMD}"),
           _fila(229498, 229497, "10:00:01", CMD),
           _fila(229787, 1000, "11:00:00", f"/usr/lib/claude-desktop/disclaimer {CMD}"),
           _fila(229788, 229787, "11:00:01", CMD),
           _fila(2000, 1, "09:00:00", "/opt/claude-code/bin/claude"),
           _fila(2001, 2000, "12:00:00", CMD))


@pytest.fixture
def paquete(tmp_path):
    ruta = tmp_path / "site-packages" / "ratifact"
    ruta.mkdir(parents=True)
    return ruta


def _vivos(ps, tmp_path, paquete, registrados):
    registros = tmp_path / "servers"
    registros.mkdir()
    for pid, hora in registrados.items():
        _registrar(registros, pid, hora)
    return procesos.procesos_vivos(paquete, correr=lambda: ps, registros=registros)


def test_p027_dos_pares_dan_dos_servidores_con_envoltorio(tmp_path, paquete, vieja):
    vivos = _vivos(P027, tmp_path, paquete, {229498: "10:00:01", 229788: "11:00:01"})
    lineas, _ = doctor.informe(procesos=lambda: [], paquete=paquete, vivos=lambda: vivos)
    assert "Running `ratifact serve` servers: 2" in "\n".join(lineas)
    primero = next(l for l in lineas if "PID 229498" in l)
    segundo = next(l for l in lineas if "PID 229788" in l)
    assert "(wrapper 229497, claude-desktop)" in primero and "parent disclaimer" in primero
    assert "(wrapper 229787, claude-desktop)" in segundo
    assert not any(l.lstrip().startswith(("PID 229497", "PID 229787")) for l in lineas)        # not apart
    aparte = lineas[next(i for i, l in enumerate(lineas) if l.startswith("Unregistered processes")) + 1:]
    assert [l.split("·")[0].strip() for l in aparte if l.startswith("  PID")][:1] == ["PID 2001"]    # only the orphan
    assert not any("PID 229497" in l or "PID 229787" in l for l in aparte)


def test_p027_servers_with_this_configuration_usa_el_mismo_criterio(tmp_path, paquete, vieja):
    vivos = _vivos(P027, tmp_path, paquete, {229498: "10:00:01", 229788: "11:00:01"})
    todos = [Proceso(pid, CMD, None) for pid in (229497, 229498, 229787, 229788)]
    lineas, _ = doctor.informe(procesos=lambda: todos, paquete=paquete, vivos=lambda: vivos)
    assert "Running servers with this configuration: 229498, 229788" in lineas


def test_servidor_registrado_sin_envoltorio_se_ve_como_antes(tmp_path, paquete, vieja):
    vivos = _vivos(P027, tmp_path, paquete, {2001: "12:00:01"})
    lista = [p for p in vivos if p.pid == 2001]
    assert lista[0].envoltorio is None and lista[0].registrado
    lineas, _ = doctor.informe(procesos=lambda: [], paquete=paquete, vivos=lambda: lista)
    assert "  PID 2001 · started 2026-10-31 12:00:00 · parent claude" in lineas


def test_proceso_huerfano_sin_registro_va_aparte_y_no_cuenta(tmp_path, paquete, vieja):
    ps = _ps(_fila(2000, 1, "09:00:00", "/opt/claude-code/bin/claude"), _fila(2001, 2000, "12:00:00", CMD))
    vivos = _vivos(ps, tmp_path, paquete, {})
    lineas, _ = doctor.informe(procesos=lambda: [Proceso(2001, CMD, None)], paquete=paquete, vivos=lambda: vivos)
    texto = "\n".join(lineas)
    assert "Running `ratifact serve` servers: 0" in texto
    aparte = next(i for i, l in enumerate(lineas) if l.startswith("Unregistered processes (possible server from before"))
    assert "PID 2001" in lineas[aparte + 1]
    assert "the content may be identical" not in texto
    assert "Running servers with this configuration: none" in lineas


def test_sin_registro_anterior_a_la_reinstalacion_no_dispara_el_aviso_de_contenido(tmp_path, paquete, vieja):
    (paquete / "a.py").write_text("x")
    import os
    os.utime(paquete / "a.py", (4102444800, 4102444800))      # installation in the future: the process predates it
    vivos = _vivos(_ps(_fila(2001, 1, "12:00:00", CMD)), tmp_path, paquete, {})
    lineas, _ = doctor.informe(procesos=lambda: [], paquete=paquete, vivos=lambda: vivos)
    assert vivos[0].estado == procesos.DESCONOCIDO
    assert "the content may be identical" not in "\n".join(lineas)


def test_sin_listado_de_procesos_no_cambia(tmp_path, paquete, vieja):
    def falla():
        raise OSError("ps not found")
    todos = [Proceso(7, CMD, None)]
    lineas, _ = doctor.informe(procesos=lambda: todos, paquete=paquete, vivos=falla)
    assert "Running `ratifact serve` processes: cannot be listed (ps not found)" in lineas
    assert "Running servers with this configuration: 7" in lineas        # not filtered (T-016)
