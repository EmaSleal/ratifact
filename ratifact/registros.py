"""Registros con frontmatter (ADR, pendientes, tareas): lectura/escritura atómica, commits de git, ids y slugs,
idempotencia de creación (ADR-019) y vistas generadas (DECISIONS.md, OPEN.md). Formato del esquema v2: carpetas,
claves y estados en inglés (ratifact.vocabulario)."""
from __future__ import annotations

import datetime as _dt
import os
import re
import subprocess
from pathlib import Path

from ratifact.config import ErrorMemoria, _es_repo, _mem, _raiz, _repo_de
from ratifact.vocabulario import DECISIONES, PENDIENTES, TAREAS, VISTA_ABIERTOS, VISTA_DECISIONES


def _escribir_atomico(ruta: Path, texto: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, ruta)


def _commit(proyecto: str, rutas: list[Path], mensaje: str) -> str:
    """Versiona cada ruta en su repositorio: .project/ tiene repo propio (independiente de la rama
    del código); el resto (p. ej. docs/) va al repositorio del proyecto. `raiz` se resuelve recién si hace
    falta (alguna ruta queda fuera de la memoria): así registrar_pendiente/registrar_decision, que solo
    escriben en la memoria, funcionan aunque la carpeta de código ya no exista (ADR-010: la memoria es
    independiente de la ruta del código)."""
    mem = _mem(proyecto)
    raiz = None
    grupos: dict[Path, list[str]] = {}
    for r in rutas:
        en_mem = r == mem or mem in r.parents
        if en_mem:
            repo = mem
        else:
            if raiz is None:
                raiz = _raiz(proyecto)
            repo = _repo_de(r.parent, raiz) or raiz
        grupos.setdefault(repo, []).append(str(r.relative_to(repo)))
    resultados = []
    for repo, rel in grupos.items():
        if not _es_repo(repo):
            resultados.append("(no git)")
            continue
        def git(*a):
            return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        git("add", "--", *rel)
        r = git("commit", "-q", "-m", f"memoria: {mensaje}", "--", *rel)
        if r.returncode != 0:
            salida = (r.stdout + r.stderr).strip()
            resultados.append("(no changes)" if "nothing" in salida or "nada" in salida
                              else f"(git failed: {salida[:200]})")
        else:
            resultados.append(git("rev-parse", "--short", "HEAD").stdout.strip())
    return " ".join(resultados)


def _hoy() -> str:
    return _dt.date.today().isoformat()


def _ahora() -> _dt.datetime:
    """Hora actual con resolución de segundos. Separada de `_hoy()` (solo fecha) porque la ventana de
    idempotencia de creación (ADR-019) necesita hora; las pruebas la monkeypatchean para simular el paso
    del tiempo sin usar `time.sleep`."""
    return _dt.datetime.now()


# ───────────────────────── registros con frontmatter ─────────────────────────

def _leer_registro(ruta: Path) -> tuple[dict, str]:
    texto = ruta.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", texto, re.S)
    if not m:
        return {}, texto
    meta = {}
    for linea in m.group(1).splitlines():
        if ":" in linea:
            k, v = linea.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def _escribir_registro(ruta: Path, meta: dict, cuerpo: str) -> None:
    cab = "\n".join(f"{k}: {' '.join(str(v).split())}" for k, v in meta.items())
    _escribir_atomico(ruta, f"---\n{cab}\n---\n{cuerpo.strip()}\n")


def _siguiente_id(carpeta: Path, prefijo: str) -> str:
    nums = [int(m.group(1)) for p in carpeta.glob(f"{prefijo}-*.md")
            if (m := re.match(rf"{prefijo}-(\d+)", p.stem))]
    return f"{prefijo}-{(max(nums) + 1 if nums else 1):03d}"


def _normalizar_id(id_: str) -> str:
    """"adr-18" → "ADR-018", "T-1" → "T-001"; 4+ cifras quedan tal cual ("ADR-1000"). Sin forma PREFIJO-número,
    solo pasa a mayúsculas."""
    m = re.fullmatch(r"([A-Za-z]+)-(\d+)", id_.strip())
    return f"{m.group(1).upper()}-{int(m.group(2)):03d}" if m else id_.strip().upper()


def _ids_resuelve(texto: str) -> list[tuple[str, bool]]:
    """`resuelve` de una tarea (ADR-027): "P-36, p-037 (parcial)" → [("P-036", False), ("P-037", True)]. Acepta
    "(parcial)" y "(partial)" sin distinguir mayúsculas ni espacios; ids normalizados, sin repetidos (gana el primero).
    No valida existencia."""
    salida: dict[str, bool] = {}
    for parte in texto.split(","):
        m = re.fullmatch(r"(.*?)\s*(\(\s*(?:parcial|partial)\s*\))?", parte.strip(), re.I)
        if m.group(1):
            salida.setdefault(_normalizar_id(m.group(1)), bool(m.group(2)))
    return list(salida.items())


def _texto_resuelve(ids: list[tuple[str, bool]]) -> str:
    """Forma guardada en el frontmatter (`resolves`): "P-036, P-037 (partial)"."""
    return ", ".join(id_ + (" (partial)" if parcial else "") for id_, parcial in ids)


def _numero_id(id_: str) -> int | None:
    """Parte numérica de un id o nombre de archivo ("ADR-1000-slug" → 1000), para ordenar y comparar numéricamente."""
    m = re.match(r"[A-Za-z]+-(\d+)", id_.strip())
    return int(m.group(1)) if m else None


def _clave_id(nombre: str) -> tuple[int, str]:
    """Clave de orden numérico por id ("ADR-101" antes que "ADR-1000"); el nombre desempata."""
    return _numero_id(nombre) or 0, nombre


def _buscar_registro(carpeta: Path, id_: str) -> Path:
    """Búsqueda exacta: solo "<ID>.md" o "<ID>-*.md" con el id normalizado ("ADR-01" nunca es ADR-010)."""
    objetivo = _normalizar_id(id_)
    candidatos = sorted(p for p in carpeta.glob("*.md")
                        if p.name == f"{objetivo}.md" or p.name.startswith(f"{objetivo}-")) if carpeta.exists() else []
    if not candidatos:
        raise ErrorMemoria(f"{objetivo} does not exist.")
    return candidatos[0]


def _slug(t: str) -> str:
    t = t.lower()
    for a, b in zip("áéíóúñü", "aeiounu"):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]


# ───────────────────────── idempotencia de creación (ADR-019) ─────────────────────────
# registrar_decision / registrar_pendiente / registrar_tarea son idempotentes dentro de esta ventana: el cliente
# (p. ej. Claude Desktop, timeout de 120s) puede perder la respuesta sin que el modelo sepa si el servidor llegó
# a ejecutar, y reintentar a ciegas no debe duplicar el registro. Se detecta por (proyecto, tipo, título
# normalizado, antigüedad) — sin idempotency key del cliente (fuera de alcance v1).
VENTANA_IDEMPOTENCIA_MINUTOS = 10
MARCA_DUPLICADO = "was already registered"


def _normalizar_titulo(t: str) -> str:
    """Case-insensitive, recorta los extremos y colapsa espacios internos, para que "Usar Godot " y
    "usar   godot" se reconozcan como el mismo título."""
    return re.sub(r"\s+", " ", t.strip().lower())


def _duplicado_reciente(carpeta: Path, prefijo: str, campo: str, valor: str, estado_inicial: str) -> dict | None:
    """Si ya existe un registro `{prefijo}-*.md` en `carpeta` con el mismo título normalizado en `campo`,
    TODAVÍA en su estado inicial (`estado_inicial`: "proposed" para ADR, "open" para pendientes,
    "todo" para tareas) y creado dentro de VENTANA_IDEMPOTENCIA_MINUTOS, devuelve su frontmatter (el
    más reciente, si hay más de uno); si no hay ninguno, None. El prefijo (ADR/P/T) ya aísla los tipos entre
    sí: un ADR y una tarea con el mismo título textual nunca son duplicados entre sí. Registros sin `created`
    (de antes de ADR-019) nunca cuentan como duplicado. Un registro que YA cambió de estado (rejected,
    superseded, closed, in_progress, merged, etc.) significa que un humano ya intervino: no es un
    reintento perdido, así que nunca cuenta como duplicado aunque sea reciente."""
    if not carpeta.exists():
        return None
    objetivo = _normalizar_titulo(valor)
    limite = _ahora() - _dt.timedelta(minutes=VENTANA_IDEMPOTENCIA_MINUTOS)
    encontrados = []
    for p in carpeta.glob(f"{prefijo}-*.md"):
        meta, _ = _leer_registro(p)
        if _normalizar_titulo(meta.get(campo, "")) != objetivo:
            continue
        if meta.get("status") != estado_inicial:
            continue
        creado = meta.get("created")
        if not creado:
            continue
        try:
            ts = _dt.datetime.fromisoformat(creado)
        except ValueError:
            continue
        if ts >= limite:
            encontrados.append((ts, meta))
    return max(encontrados, key=lambda par: par[0])[1] if encontrados else None


def _mensaje_duplicado(id_: str, extra: str = "") -> str:
    base = (f"{id_} {MARCA_DUPLICADO}: a record with this title was created less than "
            f"{VENTANA_IDEMPOTENCIA_MINUTOS} minutes ago; nothing new was created.")
    return f"{base}\n{extra}" if extra else base


def _regenerar_vistas(proyecto: str) -> list[Path]:
    """DECISIONS.md y OPEN.md se reconstruyen siempre desde los registros."""
    return _regenerar_vistas_en(_mem(proyecto))


def _regenerar_vistas_en(mem: Path) -> list[Path]:
    dec, pen = mem / DECISIONES, mem / PENDIENTES
    dec.mkdir(parents=True, exist_ok=True)
    pen.mkdir(parents=True, exist_ok=True)

    grupos = {"accepted": [], "proposed": [], "superseded": [], "rejected": []}
    for p in sorted(dec.glob("ADR-*.md"), key=lambda a: _clave_id(a.name)):
        m, _ = _leer_registro(p)
        linea = f"- **{m.get('id')}** {m.get('title')} — {m.get('summary', '')} ({m.get('date')}) → `{DECISIONES}/{p.name}`"
        if m.get("status") == "superseded":
            linea += f" · superseded by {_normalizar_id(m.get('superseded_by', '?'))}"
        grupos.setdefault(m.get("status", "proposed"), []).append(linea)
    acuerdos = ["# Decisions", "", "_View generated by memoria-proyectos. Do not edit by hand._", ""]
    for titulo, clave in (("Accepted (in force)", "accepted"), ("Proposed (not yet accepted)", "proposed"),
                          ("Superseded", "superseded"), ("Rejected", "rejected")):
        acuerdos += [f"## {titulo}", *(grupos.get(clave) or ["- (none)"]), ""]

    abiertas, cerradas = [], []
    for p in sorted(pen.glob("P-*.md"), key=lambda a: _clave_id(a.name)):
        m, cuerpo = _leer_registro(p)
        if m.get("status") == "open":
            dueno = f" · owner: {m['owner']}" if m.get("owner") else ""
            abiertas.append(f"- **{m.get('id')}** {m.get('topic')}{dueno} ({m.get('date')})\n  {cuerpo.strip().splitlines()[0] if cuerpo.strip() else ''}")
        else:
            cerradas.append(f"- {m.get('id')} {m.get('topic')} (closed {m.get('closed', '?')})")
    vista_ab = ["# Open items", "", "_View generated by memoria-proyectos. Do not edit by hand._", "",
                *(abiertas or ["- (none)"]), "", "## Recently closed", *(cerradas[-5:] or ["- (none)"]),
                f"_Resolution details in {PENDIENTES}/<id>.md._", ""]

    r1, r2 = mem / VISTA_DECISIONES, mem / VISTA_ABIERTOS
    _escribir_atomico(r1, "\n".join(acuerdos))
    _escribir_atomico(r2, "\n".join(vista_ab))
    return [r1, r2]


def _resumen_tareas(proyecto: str, solo_activas: bool = True) -> list[str]:
    carpeta = _mem(proyecto) / TAREAS
    filas = []
    for p in sorted(carpeta.glob("T-*.md"), key=lambda a: _clave_id(a.name)) if carpeta.exists() else []:
        m, _ = _leer_registro(p)
        if solo_activas and m.get("status") in ("merged", "discarded"):
            continue
        rama = (f" · branch {m['branch']}" if m.get("branch") else "") + (f" in {m['repo']}/" if m.get("repo") else "")
        filas.append(f"- **{m.get('id')}** [{m.get('status')}] {m.get('title')}{rama}")
    return filas
