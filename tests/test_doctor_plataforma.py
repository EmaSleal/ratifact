"""T-020 (ADR-012): doctor avisa en Windows nativo y reconoce WSL; la plataforma se simula."""
from types import SimpleNamespace

import pytest

from test_upgrade import hogar, vieja  # noqa: F401,F811  (fixtures)

from ratifact import doctor, doctor_plataforma


@pytest.fixture
def paquete(tmp_path):
    ruta = tmp_path / "site-packages" / "ratifact"
    ruta.mkdir(parents=True)
    return ruta


def _doctor(paquete, monkeypatch, plataforma, osrelease="6.1.0-generic"):
    monkeypatch.setattr(doctor_plataforma, "sys", SimpleNamespace(platform=plataforma))   # not the global: shutil.which reads it
    monkeypatch.setattr(doctor_plataforma, "_osrelease", lambda: osrelease)
    return doctor.informe(procesos=lambda: [], paquete=paquete, vivos=lambda: [])


WSL = "5.15.153.1-microsoft-standard-WSL2"


def test_windows_nativo_avisa_y_continua(paquete, vieja, monkeypatch):
    lineas, acciones = _doctor(paquete, monkeypatch, "win32")
    assert "Native Windows is not a supported platform" in lineas[1] and "WSL2" in lineas[1]
    assert "/mnt/c" in lineas[1]
    assert any(l.startswith("Projects folder:") for l in lineas)              # the diagnosis goes on
    assert not any("Windows" in a or "WSL" in a for a in acciones)             # not a pending action


def test_linux_sin_wsl_no_avisa(paquete, vieja, monkeypatch):
    lineas, _ = _doctor(paquete, monkeypatch, "linux")
    assert not any("WSL" in l or "Windows" in l for l in lineas)


def test_wsl_con_repositorio_en_home_solo_informa(paquete, vieja, monkeypatch):
    lineas, acciones = _doctor(paquete, monkeypatch, "linux", WSL)
    assert sum("Running inside WSL: supported" in l for l in lineas) == 1
    assert not any("/mnt/" in l for l in lineas)


def test_wsl_con_repositorio_bajo_mnt_advierte(paquete, vieja, monkeypatch):
    from ratifact import upgrade
    from pathlib import Path
    planificar = upgrade.planificar

    def con_mnt(*a, **k):
        plan = planificar(*a, **k)
        for p in plan.inst.proyectos:
            p.codigo = Path("/mnt/c/Users/u/repo")
        return plan
    monkeypatch.setattr(doctor, "planificar", con_mnt)
    lineas, acciones = _doctor(paquete, monkeypatch, "linux", WSL)
    assert any("under /mnt/" in l and "slow" in l for l in lineas)
    assert not any("WSL" in a for a in acciones)
