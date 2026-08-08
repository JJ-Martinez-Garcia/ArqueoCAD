"""Lectura de DXF y traducción al modelo interno.

El aplanado de curvas se delega en `ezdxf.path`, que cubre de forma uniforme
LINE, ARC, CIRCLE, ELLIPSE, LWPOLYLINE, POLYLINE y SPLINE. Reimplementarlo aquí
solo añadiría una segunda fuente de errores.

Dos criterios gobiernan este módulo:

1. **Una entidad defectuosa no invalida el archivo.** Cada conversión se aísla,
   y lo que falla se anota como aviso en lugar de interrumpir la lectura. Los
   DXF procedentes de conversión desde DWG traen con frecuencia entidades
   marginales que no deben impedir abrir el plano.
2. **Nada se pierde en silencio.** Toda simplificación queda registrada en
   `Documento.avisos`, que el usuario puede consultar.
"""

# Parte de ArqueoCAD. Copyright (C) 2026 José Javier Martínez García
#
# Este programa es software libre: puede redistribuirlo y modificarlo bajo los
# términos de la Licencia Pública General de GNU publicada por la Free Software
# Foundation, en su versión 3.
#
# Se distribuye con la esperanza de que resulte útil, pero SIN NINGUNA GARANTÍA;
# ni siquiera la garantía implícita de COMERCIABILIDAD o IDONEIDAD PARA UN FIN
# DETERMINADO. Consulte la Licencia Pública General de GNU para más detalles.
#
# Debería haber recibido una copia de la Licencia junto con este programa. Si no
# es así, véase <https://www.gnu.org/licenses/>.

from __future__ import annotations

import math
from pathlib import Path as RutaFS
from typing import Iterator

import ezdxf
from ezdxf import colors as ez_colores
from ezdxf import path as ez_path
from ezdxf import recover
from ezdxf.entities import DXFEntity
from ezdxf.lldxf.const import DXFError

from ..core.geometria import TOLERANCIA_POR_DEFECTO, Punto2D
from ..core.modelo import (
    INTERLINEADO_MTEXT,
    NOMBRE_DEFPOINTS,
    Aviso,
    Capa,
    Documento,
    Entidad,
    FormatoOrigen,
    Polilinea,
    Punto,
    Relleno,
    Texto,
)
from ..core.unidades import desde_codigo

#: Profundidad máxima al desplegar bloques anidados. Un dibujo bien construido
#: rara vez pasa de tres o cuatro niveles; un límite evita que una referencia
#: circular mal formada bloquee la aplicación.
PROFUNDIDAD_MAXIMA_BLOQUES = 8

#: Código ACI que significa «heredar el color de la capa».
ACI_POR_CAPA = 256
#: Código ACI que significa «heredar el color del bloque».
ACI_POR_BLOQUE = 0

#: Entidades que se resuelven desplegando su geometría interna en lugar de
#: interpretarlas directamente. Las cotas y las directrices son en realidad
#: bloques anónimos generados por el programa de CAD.
TIPOS_DESPLEGABLES = {"INSERT", "DIMENSION", "LEADER", "MLEADER", "MULTILEADER", "ACAD_TABLE"}


def leer_dxf(
    ruta: str | RutaFS,
    tolerancia: float = TOLERANCIA_POR_DEFECTO,
    explotar_bloques: bool = True,
) -> Documento:
    """Carga un DXF y devuelve el `Documento` correspondiente.

    Args:
        ruta: archivo a leer.
        tolerancia: separación máxima admitida entre una curva y la poligonal
            que la sustituye, en unidades de dibujo.
        explotar_bloques: si se despliegan las referencias de bloque para
            repartir su geometría entre las capas reales. Al desactivarlo, cada
            bloque se atribuye por completo a la capa de su inserción.

    Raises:
        FileNotFoundError: si el archivo no existe.
        LecturaDXFError: si el archivo no es un DXF legible.
    """
    ruta = RutaFS(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo: {ruta}")

    # `recover` tolera archivos con estructura dañada o generada por programas
    # de terceros, situación habitual en los DXF que provienen de un DWG.
    try:
        doc_ez, auditoria = recover.readfile(str(ruta))
    except IOError as exc:
        raise LecturaDXFError(f"No se puede abrir «{ruta.name}»: {exc}") from exc
    except DXFError as exc:
        raise LecturaDXFError(
            f"«{ruta.name}» no parece un DXF válido: {exc}"
        ) from exc

    documento = Documento(
        ruta=str(ruta),
        formato=FormatoOrigen.DXF,
        unidad=desde_codigo(doc_ez.header.get("$INSUNITS", 0)),
        origen_ezdxf=doc_ez,
    )

    if auditoria.has_errors:
        documento.avisos.append(
            Aviso(
                "aviso",
                f"El archivo presentaba {len(auditoria.errors)} problemas de estructura que se han reparado al abrirlo.",
                "El dibujo se ha recuperado; conviene revisar el resultado antes de exportar.",
            )
        )

    if documento.unidad == 0:
        documento.avisos.append(
            Aviso(
                "aviso",
                "El archivo no declara sus unidades de dibujo.",
                "Habrá que indicarlas a mano antes de exportar a SVG si se quiere conservar la escala.",
            )
        )

    _leer_capas(doc_ez, documento)
    _leer_entidades(doc_ez, documento, tolerancia, explotar_bloques)
    _avisar_de_presentaciones(doc_ez, documento)

    documento.recalcular_estadisticas()
    return documento


class LecturaDXFError(Exception):
    """El archivo no ha podido interpretarse como DXF."""


def _leer_capas(doc_ez, documento: Documento) -> None:
    """Vuelca la tabla de capas resolviendo ya el color a RGB."""
    for capa_ez in doc_ez.layers:
        aci = int(getattr(capa_ez.dxf, "color", 7))
        # Un ACI negativo indica capa apagada; el valor absoluto sigue siendo
        # el color.
        apagada = aci < 0
        aci = abs(aci) or 7

        color = _color_verdadero(capa_ez)
        if color is None:
            color = ez_colores.aci2rgb(aci)

        nombre = capa_ez.dxf.name
        documento.capas[nombre] = Capa(
            nombre=nombre,
            color=color,
            aci=aci,
            visible=not apagada,
            congelada=bool(capa_ez.is_frozen()),
            bloqueada=bool(capa_ez.is_locked()),
            tipo_linea=getattr(capa_ez.dxf, "linetype", "Continuous"),
            grosor=float(getattr(capa_ez.dxf, "lineweight", 0) or 0) / 100.0,
            imprimible=(
                bool(getattr(capa_ez.dxf, "plot", 1))
                and nombre.casefold() != NOMBRE_DEFPOINTS
            ),
        )


def _color_verdadero(entidad) -> tuple[int, int, int] | None:
    """Devuelve el color RGB explícito de la entidad, si lo declara.

    El color verdadero de 24 bits tiene prioridad sobre el índice ACI cuando
    ambos están presentes.
    """
    try:
        if entidad.dxf.hasattr("true_color"):
            valor = int(entidad.dxf.true_color)
            return ((valor >> 16) & 0xFF, (valor >> 8) & 0xFF, valor & 0xFF)
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def _color_de_entidad(entidad) -> tuple[int, int, int] | None:
    """Color propio de la entidad, o ``None`` si lo hereda de la capa."""
    color = _color_verdadero(entidad)
    if color is not None:
        return color

    aci = int(getattr(entidad.dxf, "color", ACI_POR_CAPA))
    if aci in (ACI_POR_CAPA, ACI_POR_BLOQUE):
        return None
    if aci < 0:
        return None
    try:
        return ez_colores.aci2rgb(aci)
    except (IndexError, ValueError):
        return None


def _leer_entidades(
    doc_ez, documento: Documento, tolerancia: float, explotar_bloques: bool
) -> None:
    """Recorre el espacio modelo y traduce cada entidad."""
    fallidas: dict[str, int] = {}

    for entidad_ez in doc_ez.modelspace():
        try:
            documento.entidades.extend(
                _convertir(entidad_ez, tolerancia, explotar_bloques, 0, documento)
            )
        except Exception as exc:  # noqa: BLE001 - una entidad rota no invalida el plano
            tipo = entidad_ez.dxftype()
            fallidas[tipo] = fallidas.get(tipo, 0) + 1
            documento.avisos.append(
                Aviso(
                    "error",
                    f"No se ha podido interpretar una entidad {tipo}.",
                    str(exc),
                )
            )

    if fallidas:
        resumen = ", ".join(f"{n} × {tipo}" for tipo, n in sorted(fallidas.items()))
        documento.avisos.append(
            Aviso("aviso", f"Entidades omitidas por errores de lectura: {resumen}.")
        )


def _convertir(
    entidad_ez: DXFEntity,
    tolerancia: float,
    explotar_bloques: bool,
    profundidad: int,
    documento: Documento,
) -> Iterator[Entidad]:
    """Traduce una entidad de ezdxf a una o varias primitivas del modelo."""
    tipo = entidad_ez.dxftype()
    capa = str(getattr(entidad_ez.dxf, "layer", "0"))
    color = _color_de_entidad(entidad_ez)
    handle = str(getattr(entidad_ez.dxf, "handle", "") or "")

    if tipo in TIPOS_DESPLEGABLES:
        yield from _desplegar(
            entidad_ez, tipo, capa, tolerancia, explotar_bloques, profundidad, documento
        )
        return

    if tipo == "POINT":
        p = entidad_ez.dxf.location
        yield Punto(
            capa=capa, color=color, handle=handle, tipo_origen=tipo,
            posicion=(float(p.x), float(p.y)),
        )
        return

    if tipo in ("TEXT", "MTEXT", "ATTRIB"):
        texto = _convertir_texto(entidad_ez, tipo, capa, color, handle)
        if texto is not None:
            yield texto
        return

    if tipo in ("HATCH", "MPOLYGON"):
        yield from _convertir_sombreado(entidad_ez, capa, color, handle, tolerancia)
        return

    if tipo in ("SOLID", "TRACE", "3DFACE"):
        relleno = _convertir_solido(entidad_ez, tipo, capa, color, handle)
        if relleno is not None:
            yield relleno
        return

    # Todo lo demás es geometría lineal o curva, y `ezdxf.path` la unifica.
    yield from _convertir_geometria(entidad_ez, tipo, capa, color, handle, tolerancia)


def _desplegar(
    entidad_ez: DXFEntity,
    tipo: str,
    capa: str,
    tolerancia: float,
    explotar_bloques: bool,
    profundidad: int,
    documento: Documento,
) -> Iterator[Entidad]:
    """Despliega bloques, cotas y directrices en su geometría real.

    `virtual_entities` aplica la transformación de inserción sin alterar el
    documento de origen, que debe permanecer intacto para la exportación a DXF.
    """
    if profundidad >= PROFUNDIDAD_MAXIMA_BLOQUES:
        documento.avisos.append(
            Aviso(
                "aviso",
                f"Se ha alcanzado el límite de anidamiento de bloques en un {tipo}.",
                f"Los bloques por debajo del nivel {PROFUNDIDAD_MAXIMA_BLOQUES} no se han desplegado.",
            )
        )
        return

    try:
        hijas = list(entidad_ez.virtual_entities())
    except Exception as exc:  # noqa: BLE001
        documento.avisos.append(
            Aviso("error", f"No se ha podido desplegar un {tipo}.", str(exc))
        )
        return

    for hija in hijas:
        for primitiva in _convertir(
            hija, tolerancia, explotar_bloques, profundidad + 1, documento
        ):
            # Sin explosión, toda la geometría del bloque se atribuye a la capa
            # donde se insertó; con explosión se respeta la capa de cada pieza.
            if not explotar_bloques:
                primitiva.capa = capa
            # Una entidad interna en la capa «0» hereda la capa de inserción:
            # así lo define el formato, y es lo que hace que un bloque adopte el
            # aspecto del lugar donde se coloca.
            elif primitiva.capa == "0":
                primitiva.capa = capa
            yield primitiva


def _convertir_geometria(
    entidad_ez: DXFEntity,
    tipo: str,
    capa: str,
    color: tuple[int, int, int] | None,
    handle: str,
    tolerancia: float,
) -> Iterator[Polilinea]:
    """Aplana cualquier entidad lineal o curva a una o varias polilíneas."""
    try:
        camino = ez_path.make_path(entidad_ez)
    except (TypeError, ValueError, AttributeError):
        return  # Tipo no soportado por ezdxf.path; queda fuera del dibujo.

    for sub in camino.sub_paths() if camino.has_sub_paths else [camino]:
        puntos = [(float(v.x), float(v.y)) for v in sub.flattening(tolerancia)]
        if len(puntos) < 2:
            continue
        cerrada = _es_cerrada(puntos)
        if cerrada:
            puntos.pop()  # El cierre se marca con la bandera, no repitiendo vértice.
        yield Polilinea(
            capa=capa, color=color, handle=handle, tipo_origen=tipo,
            puntos=puntos, cerrada=cerrada,
        )


def _es_cerrada(puntos: list[Punto2D], epsilon: float = 1e-9) -> bool:
    if len(puntos) < 3:
        return False
    (x0, y0), (xn, yn) = puntos[0], puntos[-1]
    return math.isclose(x0, xn, abs_tol=epsilon) and math.isclose(y0, yn, abs_tol=epsilon)


def _convertir_texto(
    entidad_ez: DXFEntity,
    tipo: str,
    capa: str,
    color: tuple[int, int, int] | None,
    handle: str,
) -> Texto | None:
    """Reduce TEXT, MTEXT y ATTRIB a una cadena con posición y altura."""
    interlineado = INTERLINEADO_MTEXT

    if tipo == "MTEXT":
        # `plain_text` traduce los códigos de formato a texto llano y convierte
        # los saltos «\P» en saltos de línea reales, que deben conservarse.
        contenido = entidad_ez.plain_text(split=False)
        posicion = entidad_ez.dxf.insert
        altura = float(entidad_ez.dxf.char_height)
        rotacion = float(getattr(entidad_ez.dxf, "rotation", 0.0))
        factor = float(getattr(entidad_ez.dxf, "line_spacing_factor", 1.0) or 1.0)
        interlineado = INTERLINEADO_MTEXT * factor
    else:
        contenido = str(entidad_ez.dxf.text)
        # `align_point` manda sobre `insert` en los textos alineados; cuando no
        # está definido, se usa el punto de inserción.
        posicion = entidad_ez.dxf.get("align_point") or entidad_ez.dxf.insert
        altura = float(entidad_ez.dxf.height)
        rotacion = float(getattr(entidad_ez.dxf, "rotation", 0.0))

    contenido = contenido.strip()
    if not contenido:
        return None

    return Texto(
        capa=capa, color=color, handle=handle, tipo_origen=tipo,
        contenido=contenido,
        posicion=(float(posicion.x), float(posicion.y)),
        altura=altura if altura > 0 else 1.0,
        rotacion=rotacion,
        interlineado=interlineado,
    )


def _convertir_sombreado(
    entidad_ez: DXFEntity,
    capa: str,
    color: tuple[int, int, int] | None,
    handle: str,
    tolerancia: float,
) -> Iterator[Relleno]:
    """Extrae los contornos de un sombreado.

    El patrón de relleno de AutoCAD no tiene equivalente en SVG y no se
    reconstruye: se conserva el contorno y, si el relleno era sólido, la marca
    para poder pintarlo.
    """
    try:
        caminos = ez_path.from_hatch(entidad_ez)
    except Exception:  # noqa: BLE001
        return

    contornos: list[list[Punto2D]] = []
    for camino in caminos:
        for sub in camino.sub_paths() if camino.has_sub_paths else [camino]:
            puntos = [(float(v.x), float(v.y)) for v in sub.flattening(tolerancia)]
            if len(puntos) >= 3:
                contornos.append(puntos)

    if not contornos:
        return

    yield Relleno(
        capa=capa, color=color, handle=handle, tipo_origen=entidad_ez.dxftype(),
        contornos=contornos,
        solido=bool(getattr(entidad_ez.dxf, "solid_fill", 0)),
        patron=str(getattr(entidad_ez.dxf, "pattern_name", "") or ""),
    )


def _convertir_solido(
    entidad_ez: DXFEntity,
    tipo: str,
    capa: str,
    color: tuple[int, int, int] | None,
    handle: str,
) -> Relleno | None:
    """Convierte SOLID, TRACE y 3DFACE, que son cuadriláteros de cuatro vértices.

    El orden de los vértices en SOLID y TRACE dibuja un reloj de arena si se
    toma tal cual, porque el tercero y el cuarto van intercambiados respecto al
    recorrido del contorno.
    """
    try:
        v = [entidad_ez.dxf.vtx0, entidad_ez.dxf.vtx1, entidad_ez.dxf.vtx2, entidad_ez.dxf.vtx3]
    except AttributeError:
        return None

    puntos = [(float(p.x), float(p.y)) for p in v]
    if tipo in ("SOLID", "TRACE"):
        puntos = [puntos[0], puntos[1], puntos[3], puntos[2]]

    # Un cuadrilátero degenerado en triángulo repite el último vértice.
    unicos: list[Punto2D] = []
    for p in puntos:
        if not unicos or not (
            math.isclose(p[0], unicos[-1][0], abs_tol=1e-12)
            and math.isclose(p[1], unicos[-1][1], abs_tol=1e-12)
        ):
            unicos.append(p)
    if len(unicos) < 3:
        return None

    return Relleno(
        capa=capa, color=color, handle=handle, tipo_origen=tipo,
        contornos=[unicos], solido=True,
    )


def _avisar_de_presentaciones(doc_ez, documento: Documento) -> None:
    """Advierte de que las presentaciones no se leen en esta versión.

    Los planos de excavación suelen tener la geometría en el espacio modelo,
    pero las carátulas y los cajetines viven en las presentaciones y su
    ausencia debe quedar clara.
    """
    con_contenido = []
    for nombre in doc_ez.layout_names_in_taborder():
        if nombre.lower() == "model":
            continue
        try:
            if len(doc_ez.layout(nombre)) > 0:
                con_contenido.append(nombre)
        except Exception:  # noqa: BLE001
            continue

    if con_contenido:
        documento.avisos.append(
            Aviso(
                "info",
                f"El archivo tiene {len(con_contenido)} presentaciones con contenido que no se han cargado.",
                "Solo se lee el espacio modelo: " + ", ".join(con_contenido) + ".",
            )
        )
