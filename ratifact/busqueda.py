"""Respuesta de buscar con cuotas por sección (T-007): primero los registros del catálogo (id exacto y hasta 5
títulos), luego las líneas de la memoria y después las del código. El presupuesto que deja el catálogo se reparte a
partes iguales entre memoria y código, y lo que un lado no usa pasa al otro; así la memoria nunca tapa al código.
Se recorren todos los archivos (con el mismo tope de tamaño de siempre) para contar lo omitido por sección.

Revisión 2 — dentro de cada sección:
- Orden de archivos: primero los cuyo nombre coincide con `texto` (ver _nombre_coincide), luego el resto; cada grupo
  en orden de ruta. Un archivo cuyo nombre coincide pero ninguna línea sale una vez como
  "<ruta>: (coincide el nombre del archivo)". En la memoria, los registros (.project/<carpeta>/<ID>-…) no coinciden
  por nombre: ya los cubre el catálogo.
- Diversidad: la primera pasada toma la primera línea de cada archivo en ese orden; solo si sobra cupo, la segunda
  agrega las demás líneas de esos archivos, agrupadas por archivo en el mismo orden. Así las primeras N líneas de
  una sección son N archivos distintos (si los hay).
- La línea final cuenta líneas omitidas y, si algún archivo con coincidencias quedó sin ninguna línea, también
  archivos omitidos ("memoria 41 líneas/9 archivos, código 147 líneas/23 archivos"); si no quedó ninguno, conserva
  la forma anterior ("memoria 25, código 35"). La marca de coincidencia por nombre cuenta como una línea."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ratifact.catalogo import CARPETAS, _coincidencias, _linea, _plano
from ratifact.config import EXT_TEXTO, LIMITE_ARCHIVO_BUSQUEDA

LINEA_TITULO = re.compile(r"(titulo|tema):")
MARCA_NOMBRE = "(coincide el nombre del archivo)"


def _nombre_coincide(nombre: str, texto: str) -> bool:
    """¿`texto` empieza en un inicio de palabra del `nombre` (sin extensión)? Los inicios se calculan sobre el nombre
    ORIGINAL: el primer carácter alfanumérico, el que sigue a uno no alfanumérico (espacio, "_", "-", "." …) y una
    mayúscula precedida de minúscula o dígito (camelCase: "AsientoContableService" → asiento|contable|service; "ACME"
    es una sola palabra). Luego se compara sin acentos ni mayúsculas y sin separadores, en ambos lados: así una
    consulta de varias palabras ("contable service") coincide si sus palabras siguen seguidas en el nombre desde un
    inicio. "ontable" no coincide con "AsientoContableService"; "id" no coincide con "Hibrido"."""
    buscado = "".join(c for c in _plano(texto) if c.isalnum())
    if not buscado:
        return False
    plano, inicios, previo = "", [], ""
    for c in nombre:
        if unicodedata.combining(c):
            continue
        if c.isalnum() and (not previo.isalnum() or (c.isupper() and (previo.islower() or previo.isdigit()))):
            inicios.append(len(plano))
        plano += "".join(x for x in _plano(c) if x.isalnum())
        previo = c
    return any(plano.startswith(buscado, i) for i in inicios)


def _es_registro(relativa: str) -> bool:
    """¿`relativa` (dentro de la memoria) es un registro: <carpeta de registros>/<PREFIJO>-<n>…?"""
    partes = relativa.split("/")
    return len(partes) == 2 and partes[0] in CARPETAS and bool(re.match(rf"{CARPETAS[partes[0]]}-\d+", partes[1]))


def _fin_frontmatter(lineas: list[str]) -> int:
    """Número de la línea que cierra el frontmatter ("---"), o 0 si el archivo no empieza con uno."""
    if not lineas or lineas[0].strip() != "---":
        return 0
    return next((n for n, l in enumerate(lineas[1:], 2) if l.strip() == "---"), 0)


def _archivos_con_coincidencias(base: Path, prefijo: str, archivos: list[Path], texto: str, patron: re.Pattern,
                                limite: int, registros_mostrados: frozenset[str] = frozenset(),
                                memoria: bool = False) -> list[tuple[list[str], int]]:
    """Por cada archivo con coincidencias (primero los que coinciden por nombre): sus primeras `limite` líneas
    "ruta:n: texto" que contienen `patron` y cuántas tiene en total. En los archivos de `registros_mostrados` (rutas
    ya listadas por el catálogo) no se repite la línea titulo/tema del frontmatter. Cada archivo se lee una sola vez."""
    por_nombre, otros = [], []
    for p in archivos:
        if p.suffix not in EXT_TEXTO:
            continue
        relativa = p.relative_to(base).as_posix()
        ruta = f"{prefijo}{relativa}"
        nombre = not (memoria and _es_registro(relativa)) and _nombre_coincide(p.stem, texto)
        try:
            if p.stat().st_size > LIMITE_ARCHIVO_BUSQUEDA:
                continue
            contenido = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not nombre and not patron.search(contenido):
            continue
        filas = contenido.splitlines()
        fin = _fin_frontmatter(filas) if ruta in registros_mostrados else 0
        lineas, total = [], 0
        for n, linea in enumerate(filas, 1):
            if not patron.search(linea) or (n < fin and LINEA_TITULO.match(linea)):
                continue
            total += 1
            if len(lineas) < limite:
                lineas.append(f"{ruta}:{n}: {linea.strip()[:200]}")
        if not total and nombre:
            lineas, total = [f"{ruta}: {MARCA_NOMBRE}"], 1
        if total:
            (por_nombre if nombre else otros).append((lineas, total))
    return por_nombre + otros


def _elegir(archivos: list[tuple[list[str], int]], n: int) -> tuple[list[str], int]:
    """Hasta `n` líneas: primera pasada, una por archivo en orden; segunda (si sobra cupo), las demás agrupadas por
    archivo. Devuelve también cuántos archivos tienen al menos una línea mostrada."""
    primera = [lineas[0] for lineas, _ in archivos[:max(n, 0)]]
    segunda = [l for lineas, _ in archivos for l in lineas[1:]][:max(n - len(primera), 0)]
    return primera + segunda, len(primera)


def _resultados(proyecto: str, texto: str, max_resultados: int, memoria: tuple[Path, str, list[Path]],
                codigo: tuple[Path, str, list[Path]]) -> str:
    """`memoria` y `codigo`: (carpeta base, prefijo de ruta, archivos)."""
    tope = max(max_resultados, 0)
    registros, titulos_fuera = _coincidencias(proyecto, texto)
    catalogo = [_linea(r) for r in registros[:tope]]
    resto = tope - len(catalogo)
    patron = re.compile(re.escape(texto), re.I)
    en_memoria = _archivos_con_coincidencias(*memoria, texto, patron, resto,
                                             frozenset(r.ruta for r in registros[:tope]), memoria=True)
    en_codigo = _archivos_con_coincidencias(*codigo, texto, patron, resto)
    total_memoria, total_codigo = sum(t for _, t in en_memoria), sum(t for _, t in en_codigo)
    n_memoria = min(total_memoria, max((resto + 1) // 2, resto - total_codigo))
    lineas_memoria, vistos_memoria = _elegir(en_memoria, n_memoria)
    lineas_codigo, vistos_codigo = _elegir(en_codigo, min(total_codigo, resto - n_memoria))
    res = catalogo + lineas_memoria + lineas_codigo
    fuera = [(total_memoria - len(lineas_memoria), len(en_memoria) - vistos_memoria),
             (total_codigo - len(lineas_codigo), len(en_codigo) - vistos_codigo)]
    fuera_catalogo = len(registros) + titulos_fuera - len(catalogo)
    if fuera_catalogo or any(l for l, _ in fuera):
        con_archivos = any(a for _, a in fuera)
        memoria_txt, codigo_txt = (f"{l} líneas/{a} archivos" if con_archivos else f"{l}" for l, a in fuera)
        res.append(f"(… más resultados — omitidos: catálogo {fuera_catalogo}, memoria {memoria_txt}, "
                   f"código {codigo_txt}; refina la búsqueda)")
    return "\n".join(res) or "(sin coincidencias)"
