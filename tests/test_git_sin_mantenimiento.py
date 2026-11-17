"""P-042 / T-030: git no lanza mantenimiento ni gc automáticos durante la suite."""
from __future__ import annotations

import subprocess
import time

from conftest import crear_repo


def _config(repo, clave):
    r = subprocess.run(["git", "-C", str(repo), "config", "--get", clave], capture_output=True, text=True)
    return r.stdout.strip()


def test_repo_de_prueba_sin_mantenimiento_ni_gc_automaticos(entorno):
    repo = crear_repo(entorno["base"] / "otro")
    assert _config(repo, "maintenance.auto") == "false"
    assert _config(repo, "gc.auto") == "0"


def test_crear_repo_no_deja_maintenance_lock(entorno):
    repo = crear_repo(entorno["base"] / "otro")
    lock = repo / ".git" / "objects" / "maintenance.lock"
    fin = time.monotonic() + 1.0
    while time.monotonic() < fin:
        assert not lock.exists()
        time.sleep(0.05)


def test_memoria_creada_por_ratifact_hereda_sin_mantenimiento(proyecto):
    assert (proyecto["mem"] / ".git").exists()
    assert _config(proyecto["mem"], "maintenance.auto") == "false"
    assert _config(proyecto["mem"], "gc.auto") == "0"
