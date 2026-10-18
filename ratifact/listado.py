"""Listado con profundidad adaptativa para listar_documentos (ADR-023). Si el listado completo entra en el
presupuesto (LIMITE_LISTADO_ENTRADAS líneas y LIMITE_LISTADO_CARACTERES caracteres) sale igual que siempre; si no,
se expande nivel por nivel mientras entre: las carpetas sin expandir muestran cuántos archivos contienen y las
cadenas de carpetas con un solo hijo (p. ej. src/main/java/...) se colapsan en una línea. Orden determinista."""
from __future__ import annotations

from ratifact.config import LIMITE_LISTADO_CARACTERES, LIMITE_LISTADO_ENTRADAS


class _Nodo:
    def __init__(self):
        self.archivos: dict[str, int] = {}
        self.carpetas: dict[str, _Nodo] = {}
        self.total = 0


def _arbol(entradas: list[tuple[str, int]]) -> _Nodo:
    raiz = _Nodo()
    for rel, tam in entradas:
        *carpetas, nombre = rel.split("/")
        nodo = raiz
        nodo.total += 1
        for c in carpetas:
            nodo = nodo.carpetas.setdefault(c, _Nodo())
            nodo.total += 1
        nodo.archivos[nombre] = tam
    return raiz


def _entra(lineas: list[str]) -> bool:
    return len(lineas) <= LIMITE_LISTADO_ENTRADAS and len("\n".join(lineas)) <= LIMITE_LISTADO_CARACTERES


def _filas(nodo: _Nodo, ruta: tuple, expandidas: set, carpeta: str):
    """(clave de orden, línea, ¿carpeta sin expandir?) de lo que se ve de `nodo` con las carpetas `expandidas`."""
    for nombre, tam in nodo.archivos.items():
        yield ruta + (nombre,), f"{carpeta}/{'/'.join(ruta + (nombre,))}  ({tam} B)", False
    for nombre, hijo in nodo.carpetas.items():
        destino = ruta + (nombre,)
        while not hijo.archivos and len(hijo.carpetas) == 1:      # cadena de un solo hijo → un solo paso
            (siguiente, hijo), = hijo.carpetas.items()
            destino += (siguiente,)
        if destino in expandidas:
            yield from _filas(hijo, destino, expandidas, carpeta)
        else:
            n = hijo.total
            yield destino, f"{carpeta}/{'/'.join(destino)}/ ({n} {'archivo' if n == 1 else 'archivos'})", True


def _vista(raiz: _Nodo, expandidas: set, carpeta: str) -> list[tuple]:
    return sorted(_filas(raiz, (), expandidas, carpeta), key=lambda f: f[0])


def _listado(carpeta: str, entradas: list[tuple[str, int]]) -> str:
    """`entradas`: (ruta relativa a `carpeta` con "/", tamaño en bytes), en cualquier orden."""
    carpeta = carpeta.rstrip("/")
    completo = [f"{carpeta}/{rel}  ({tam} B)" for rel, tam in entradas]
    if _entra(completo):
        return "\n".join(completo)
    raiz = _arbol(entradas)
    nota = (f"(listado resumido: {raiz.total} archivos en total; pide una `carpeta` más específica para ver "
            "el detalle)")
    expandidas: set = set()
    vista = _vista(raiz, expandidas, carpeta)
    while True:                       # cada vuelta expande TODAS las carpetas visibles del nivel siguiente
        candidatas = expandidas | {clave for clave, _, plegada in vista if plegada}
        if candidatas == expandidas:
            break
        siguiente = _vista(raiz, candidatas, carpeta)
        if not _entra([linea for _, linea, _ in siguiente] + [nota]):
            break
        expandidas, vista = candidatas, siguiente
    lineas = [linea for _, linea, _ in vista]
    if _entra(lineas + [nota]):
        return "\n".join(lineas + [nota])
    # ni el primer nivel entra (p. ej. una carpeta plana enorme): se recorta en orden y se dice cuánto falta
    mostradas, contados = [], 0
    for _, linea, plegada in vista:
        n = int(linea.rsplit("(", 1)[1].split()[0]) if plegada else 1
        resto = f"(… {raiz.total - contados - n} archivos más sin listar en {carpeta}/)"
        if not _entra(mostradas + [linea, resto, nota]):
            break
        mostradas.append(linea)
        contados += n
    return "\n".join(mostradas + [f"(… {raiz.total - contados} archivos más sin listar en {carpeta}/)", nota])
