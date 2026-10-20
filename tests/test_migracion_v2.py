"""Migración automática del esquema v1 → v2 (T-010; spec docs/v1-english-naming.md §2, §5, §6, §8 y addendum;
ADR-028, ADR-029, ADR-030): carpetas, claves, estados, títulos y etiquetas en inglés, con repo limpio, tag pre-v2,
un solo commit, vuelta atrás si algo falla y reversible con git. El cuerpo de los registros no cambia."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import log_git
from memoria_v1 import ARCHIVOS, foto
from ratifact import migracion_v2
from ratifact.vocabulario import CARPETAS_V1

TITULOS_MIGRADOS = {
    "## Decisión": "## Decision", "## Justificación": "## Rationale",
    "## Alternativas consideradas": "## Alternatives considered",
    "## Confirmación (2026-10-02)": "## Acceptance (2026-10-02)",
    "## Confirmación (2026-10-03, en lote)": "## Acceptance (2026-10-03, batch)",
    "## Descartada (2026-10-02)": "## Rejected (2026-10-02)", "## Resolución (2026-10-05)": "## Resolution (2026-10-05)",
    "## Objetivo": "## Goal", "## Criterios de aceptación": "## Acceptance criteria", "## Resuelve": "## Resolves",
    "## Decisiones aplicables": "## Applicable decisions", "## Archivos involucrados": "## Files involved",
    "## Fuera de alcance": "## Out of scope", "## Notas": "## Notes", "## Cómo verificar": "## How to verify",
    "## Resultado": "## Result", "### 2026-10-04 · en_revision": "### 2026-10-04 · in_review",
    "### 2026-10-06 · integrada": "### 2026-10-06 · merged",
    "### Revisión 1 · 2026-10-05 · devuelta": "### Review 1 · 2026-10-05 · changes_requested",
    "# Sesiones 2026-10-05": "# Sessions 2026-10-05",
}


def _git(mem, *a):
    return subprocess.run(["git", "-C", str(mem), *a], capture_output=True, text=True).stdout


def _migrar(srv):
    salida = srv.get_context(project="demo")
    assert "migrated to schema v2" in salida, salida
    return salida


def _leer(mem, rel):
    return (mem / rel).read_text(encoding="utf-8")


def _nueva(rel):
    carpeta, _, resto = rel.partition("/")
    return f"{CARPETAS_V1[carpeta]}/{resto}" if carpeta in CARPETAS_V1 else rel


# ───────────────────────── criterio 3: qué cambia ─────────────────────────

def test_un_commit_con_carpetas_renombradas_por_git_mv(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    _migrar(srv)
    assert log_git(mem)[0] == "memory: migrate schema v1 → v2"
    assert _git(mem, "status", "--porcelain") == ""
    for viejo, nuevo in CARPETAS_V1.items():
        assert not (mem / viejo).exists() and (mem / nuevo).is_dir()
    # git no guarda renombres: los detecta por similitud. Los registros de prueba son tan cortos que cambiar los
    # títulos baja la similitud de la mitad; con los reales (smoke) todos salen como R con el umbral por defecto.
    renombres = [l for l in _git(mem, "show", "--name-status", "--format=", "-M20%", "HEAD").splitlines()
                 if l[0] == "R"]
    assert len(renombres) == len([r for r in ARCHIVOS if r.split("/")[0] in CARPETAS_V1])
    historia = _git(mem, "log", "--follow", "-M20%", "--format=%s", "--",
                    "tasks/T-001-sincronizacion.md").splitlines()
    assert historia == ["memory: migrate schema v1 → v2", "memoria v1"]       # historia preservada


def test_claves_y_estados_del_frontmatter(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    _migrar(srv)
    t = _leer(mem, "tasks/T-001-sincronizacion.md").split("---\n")[1]
    assert t == ("id: T-001\ntitle: Sincronización diaria\nstatus: merged\ndate: 2026-10-01\n"
                 "branch: t-001-sincronizacion\nrepo: backend\nresolves: P-001 (partial)\nupdated: 2026-10-06\n"
                 "commit: abc1234\nreviews: 1\n")
    d1 = _leer(mem, "decisions/ADR-001-usar-godot.md").split("---\n")[1]
    assert d1 == ("id: ADR-001\ntitle: Usar Godot\nstatus: accepted\ndate: 2026-10-01\ncreated: 2026-10-01T10:00:00\n"
                  "summary: Motor Godot 4\naccepted: 2026-10-02\n")
    assert "status: rejected\n" in _leer(mem, "decisions/ADR-002-usar-unity.md")
    assert "rejected: 2026-10-02\n" in _leer(mem, "decisions/ADR-002-usar-unity.md")
    assert "status: superseded\n" in (d3 := _leer(mem, "decisions/ADR-003-motor-propio.md"))
    assert "superseded_by: ADR-001\n" in d3
    p2 = _leer(mem, "pending/P-002-elegir-musica.md").split("---\n")[1]
    assert p2 == ("id: P-002\ntopic: Elegir música\nstatus: closed\ndate: 2026-10-01\ncreated: 2026-10-01T09:00:00\n"
                  "closed: 2026-10-05\nresolution: Chiptune (ADR-001)\n")
    assert "status: open\n" in (p1 := _leer(mem, "pending/P-001-elegir-arte.md")) and "owner: Emanuel\n" in p1
    assert "status: todo\n" in _leer(mem, "tasks/T-002-pendiente.md")


def test_clave_desconocida_queda_igual_y_se_lista(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    _migrar(srv)
    assert "prioridad: alta\n" in _leer(mem, "decisions/ADR-004-licencia.md")
    assert "Frontmatter keys left as is: prioridad ×1" in _git(mem, "log", "-1", "--format=%b")


def test_titulos_conocidos_se_migran_y_los_libres_se_listan(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    _migrar(srv)
    textos = "\n".join(_leer(mem, _nueva(r)) for r in ARCHIVOS if r.split("/")[0] in CARPETAS_V1)
    for viejo, nuevo in TITULOS_MIGRADOS.items():
        assert f"\n{viejo}\n" not in "\n" + textos and nuevo in textos, viejo
    assert "## Ejecución 2 (commit def5678)" in textos
    cuerpo = _git(mem, "log", "-1", "--format=%b")
    assert "  ## Ejecución 2 (commit def5678) ×1" in cuerpo and "Headings left untouched (free text, 1 distinct)" in cuerpo


def test_vistas_regeneradas_esquema_e_intocables(srv, proyecto_v1):
    mem, antes = proyecto_v1["mem"], proyecto_v1["foto"]
    _migrar(srv)
    assert not (mem / "acuerdos.md").exists() and not (mem / "abiertas.md").exists()
    assert "**ADR-001** Usar Godot" in _leer(mem, "DECISIONS.md") and "## Accepted (in force)" in _leer(mem, "DECISIONS.md")
    assert "**P-001** Elegir arte · owner: Emanuel" in _leer(mem, "OPEN.md")
    assert "P-002 Elegir música (closed 2026-10-05)" in _leer(mem, "OPEN.md")
    assert json.loads(_leer(mem, "schema.json")) == {"version": 2, "content_language": "es"}
    assert json.loads(_leer(mem, "esquema.json")) == {"version": 2}                   # centinela (ADR-030)
    for rel in ("INDEX.md", "docs/notas.md", ".gitignore"):
        assert (mem / rel).read_bytes() == antes[rel], rel
    assert "Content language: es" in srv.get_context(project="demo")


# ───────────────────────── criterio 4: el cuerpo no cambia ─────────────────────────

def _cuerpo(texto):
    return texto.split("\n---\n", 1)[1] if texto.startswith("---\n") else texto


def test_cuerpos_identicos_salvo_titulos_y_etiquetas(srv, proyecto_v1):
    mem, antes = proyecto_v1["mem"], proyecto_v1["foto"]
    _migrar(srv)
    for rel, original in antes.items():
        if rel.split("/")[0] not in CARPETAS_V1:
            continue
        viejo, nuevo = _cuerpo(original.decode()).split("\n"), _cuerpo(_leer(mem, _nueva(rel))).split("\n")
        assert len(viejo) == len(nuevo), rel
        for a, b in zip(viejo, nuevo):
            if a.startswith("#"):
                assert b == TITULOS_MIGRADOS.get(a, a), (rel, a, b)
            elif a != b:
                assert (a, b) in {("**Observaciones**", "**Findings**"),
                                  ("**Criterios adicionales**", "**Additional criteria**")}, (rel, a, b)


def test_lineas_clave_valor_del_cuerpo_quedan_identicas(srv, proyecto_v1):
    """Caso real erp T-008 (`nuevos: …`) y un `estado: pendiente` en el cuerpo: solo se toca el frontmatter."""
    mem = proyecto_v1["mem"]
    _migrar(srv)
    texto = _leer(mem, "tasks/T-001-sincronizacion.md")
    assert "\nnuevos: ProveedorTipoCambio, HaciendaTipoCambioClient, TipoCambioSyncService (+ tests)\n" in texto
    assert "\nestado: pendiente\n" in texto and "\nstatus: todo\n" not in texto
    assert "\n- P-001 (parcial) · Elegir arte\n" in texto      # "(parcial)" del cuerpo es texto, no frontmatter


def test_etiquetas_solo_dentro_del_bloque_de_revision(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    _migrar(srv)
    texto = _leer(mem, "tasks/T-001-sincronizacion.md")
    notas = texto.split("## Notes\n")[1].split("##")[0]
    assert notas.startswith("**Observaciones**\n")                       # fuera de un bloque de revisión
    revision = texto.split("### Review 1 · 2026-10-05 · changes_requested\n")[1].split("\n## ")[0]
    assert "\n**Findings**\nFalta un caso.\n" in revision and "\n**Additional criteria**\nA. el caso.\n" in revision
    assert "\n**Observaciones:**\n" in revision                          # con dos puntos: no es la etiqueta
    assert revision.startswith("Corregir en la MISMA rama")              # la frase generada no se traduce
    assert "**Criterios:** todos\n**Archivos:** src/x.py" in texto        # negritas de agentes, intactas


def test_marcador_de_resultado_v1_se_sigue_reconociendo(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    salida = srv.update_task(project="demo", id="T-002", status="en_curso", result="empecé")
    assert "→ in_progress" in salida
    texto = _leer(mem, "tasks/T-002-pendiente.md")
    assert "(lo completa Claude Code al terminar)" not in texto and texto.endswith("in_progress\nempecé\n")


# ───────────────────────── criterio 2: precondiciones y tag ─────────────────────────

def test_cambios_sin_commit_impiden_migrar_y_no_tocan_nada(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    (mem / "INDEX.md").write_text("editado a mano\n")
    antes = foto(mem)
    salida = srv.list_tasks(project="demo")
    assert salida.startswith("ERROR:") and "uncommitted changes" in salida and "INDEX.md" in salida
    assert foto(mem) == antes and _git(mem, "tag") == "" and log_git(mem) == ["memoria v1"]


def test_lock_sin_versionar_no_cuenta_como_cambio(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    (mem / ".gitignore").write_text("*.tmp\n")
    subprocess.run(["git", "-C", str(mem), "commit", "-qam", "sin .lock en gitignore"], check=True)
    (mem / ".lock").write_text("")
    _migrar(srv)
    assert ".lock" not in _git(mem, "ls-files")


def test_memoria_v1_sin_git_no_se_migra(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    shutil.rmtree(mem / ".git")
    antes = foto(mem)
    salida = srv.get_context(project="demo")
    assert salida.startswith("ERROR:") and "is not a git repository" in salida
    assert foto(mem) == antes


def test_tag_pre_v2_y_siguientes_si_ya_existe(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    head = _git(mem, "rev-parse", "HEAD").strip()
    subprocess.run(["git", "-C", str(mem), "tag", "pre-v2"], check=True)
    subprocess.run(["git", "-C", str(mem), "tag", "pre-v2-2"], check=True)
    salida = _migrar(srv)
    assert "tag pre-v2-3" in salida
    assert _git(mem, "rev-parse", "pre-v2-3").strip() == head


# ───────────────────────── criterios 6, 7 y 8 ─────────────────────────

def test_falla_a_mitad_restaura_y_el_siguiente_acceso_reintenta(srv, proyecto_v1, monkeypatch):
    mem, antes = proyecto_v1["mem"], proyecto_v1["foto"]
    real, llamadas = migracion_v2._migrar_registro, []

    def falla_en_el_tercero(ruta, tipo, informe):
        llamadas.append(ruta)
        if len(llamadas) == 3:
            raise OSError("disco lleno")
        real(ruta, tipo, informe)
    monkeypatch.setattr(migracion_v2, "_migrar_registro", falla_en_el_tercero)
    salida = srv.add_pending(project="demo", topic="T", context="c")
    assert salida.startswith("ERROR:") and "disco lleno" in salida and "retried on the next call" in salida
    assert foto(mem) == antes and _git(mem, "status", "--porcelain") == ""
    assert log_git(mem) == ["memoria v1"] and _git(mem, "tag") == ""
    monkeypatch.setattr(migracion_v2, "_migrar_registro", real)
    assert "migrated to schema v2" in srv.add_pending(project="demo", topic="T", context="c")
    assert _git(mem, "tag").split() == ["pre-v2"]


def test_carpeta_v1_vacia_vuelve_tras_una_falla(srv, proyecto_v1, monkeypatch):
    mem = proyecto_v1["mem"]
    (mem / "sesiones" / "2026-10-05.md").unlink()
    subprocess.run(["git", "-C", str(mem), "commit", "-qam", "sin sesiones"], check=True)
    assert (mem / "sesiones").is_dir() and not any((mem / "sesiones").iterdir())     # vacía, sin versionar
    monkeypatch.setattr(migracion_v2, "_regenerar_vistas_en", lambda m: (_ for _ in ()).throw(OSError("falla")))
    assert srv.get_context(project="demo").startswith("ERROR:")
    assert (mem / "sesiones").is_dir() and not (mem / "sessions").exists()


def test_v2_no_se_migra_de_nuevo(srv, proyecto_v1):
    mem = proyecto_v1["mem"]
    _migrar(srv)
    historial = log_git(mem)
    assert "migrated" not in srv.get_context(project="demo")
    assert log_git(mem) == historial


def test_reversible_con_git_checkout_pre_v2(srv, proyecto_v1):
    mem, antes = proyecto_v1["mem"], proyecto_v1["foto"]
    arbol = _git(mem, "rev-parse", "HEAD^{tree}")
    _migrar(srv)
    subprocess.run(["git", "-C", str(mem), "checkout", "-q", "pre-v2"], check=True)
    assert foto(mem) == antes and _git(mem, "rev-parse", "HEAD^{tree}") == arbol


def test_herramienta_de_solo_lectura_tambien_migra(srv, proyecto_v1):
    salida = srv.list_tasks(project="demo")
    assert "migrated to schema v2" in salida and "**T-002** [todo] Tarea nueva" in salida


# ───────────────────────── memorias reales (solo copias; se omite si no están) ─────────────────────────

REALES = {"game": Path.home() / "Projects/game/.project",
          "memoria-proyectos": Path.home() / "Projects/.memorias/memoria-proyectos",
          "fractall": Path.home() / "Projects/.memorias/fractall",
          "erp_spring_manager": Path.home() / "Projects/.memorias/erp_spring_manager"}


@pytest.mark.skipif(not all((p / "esquema.json").exists() and not (p / "schema.json").exists()
                            for p in REALES.values()), reason="sin las memorias v1 del usuario")
def test_copias_de_las_memorias_reales(srv, proyecto, tmp_path):
    """Las 22 etiquetas reales de revisión migran y el resto del cuerpo queda igual (sobre copias)."""
    etiquetas = 0
    for nombre, real in REALES.items():
        mem = proyecto["mem"]
        shutil.rmtree(mem)
        subprocess.run(["cp", "-a", str(real), str(mem)], check=True)
        _migrar(srv)
        for p in (mem / "tasks").glob("T-*.md"):
            original = _git(mem, "show", f"pre-v2:tareas/{p.name}").split("\n")
            for a, b in zip(original, p.read_text(encoding="utf-8").split("\n")):
                etiquetas += a != b and b in ("**Findings**", "**Additional criteria**")
        if nombre == "erp_spring_manager":       # el caso real de criterio 4: línea `clave: valor` en el cuerpo
            t008 = next((mem / "tasks").glob("T-008-*.md")).read_text(encoding="utf-8")
            assert "\nnuevos: ProveedorTipoCambio, HaciendaTipoCambioClient, TipoCambioSyncService (+ tests)\n" in t008
    assert etiquetas >= 22
