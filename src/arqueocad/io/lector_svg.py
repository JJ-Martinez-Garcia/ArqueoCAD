"""Lectura de SVG y traducción al modelo interno.

Tres asuntos gobiernan este módulo, y ninguno es evidente:

**El eje Y va al revés.** En SVG crece hacia abajo y en CAD hacia arriba. La
conversión lo voltea tomando como referencia la altura del documento, de manera
que el dibujo conserve su orientación y las coordenadas queden positivas.

**Las capas no son grupos.** Solo un grupo con ``inkscape:groupmode="layer"``
cuenta como capa; el resto son agrupaciones de dibujo. Un SVG sin capas
declaradas se lee como una sola capa, y se avisa.

**La escala ya viene resuelta.** `svgelements` aplica la transformación del
``viewBox`` al viewport y entrega las coordenadas en píxeles CSS. Convertirlas a
milímetros es, por tanto, una simple constante —los 96 ppp que fija el CSS— y no
un factor que haya que deducir del ``width``. Volver a aplicar la escala del
archivo multiplicaría las medidas por varios miles.
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
import xml.etree.ElementTree as ET
from pathlib import Path as RutaFS
from typing import Iterator

from svgelements import SVG, Circle, Ellipse, Group, Path, Polygon, Polyline
from svgelements import Rect, Shape, SimpleLine, SVGText

from ..core.geometria import TOLERANCIA_POR_DEFECTO, Punto2D
from ..core.modelo import (
    Aviso,
    Capa,
    Documento,
    Entidad,
    FormatoOrigen,
    Polilinea,
    Texto,
)
from ..core.unidades import MM_POR_PIXEL_CSS, Unidad

ESPACIO_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"
ESPACIO_SVG = "http://www.w3.org/2000/svg"

#: Nombre de la capa que recoge lo que está fuera de cualquier capa declarada.
CAPA_POR_DEFECTO = "SVG"

#: Segmentos máximos por curva. Evita que un trazo larguísimo con tolerancia
#: fina genere cientos de miles de puntos.
MAX_SEGMENTOS = 400

#: Puntos por debajo de los cuales una curva no se subdivide más.
MIN_SEGMENTOS = 2

#: Suelo de la tolerancia, como fracción del lado mayor del dibujo. Una
#: tolerancia absoluta no sirve aquí: la misma media micra que es razonable en
#: un despiece de detalle obliga a partir cada círculo en cientos de tramos
#: cuando el plano mide decenas de metros, y la lectura pasa de un segundo a
#: medio minuto sin ganancia visible.
FRACCION_TOLERANCIA = 1e-5


class LecturaSVGError(Exception):
    """El archivo no ha podido interpretarse como SVG."""


def leer_svg(
    ruta: str | RutaFS,
    tolerancia: float = TOLERANCIA_POR_DEFECTO,
) -> Documento:
    """Carga un SVG y devuelve el `Documento` correspondiente."""
    ruta = RutaFS(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo: {ruta}")

    documento = Documento(ruta=str(ruta), formato=FormatoOrigen.SVG)

    try:
        svg = SVG.parse(str(ruta), reify=True)
    except Exception as exc:  # noqa: BLE001
        raise LecturaSVGError(
            f"«{ruta.name}» no parece un SVG válido: {exc}"
        ) from exc

    factor_mm = _factor(ruta, documento)
    if factor_mm is not None:
        documento.unidad = Unidad.MILIMETROS

    # Altura del viewport en píxeles: es la referencia para voltear el eje Y,
    # y debe estar en las mismas unidades que las coordenadas que entrega
    # svgelements.
    alto = float(getattr(svg, "height", 0) or 0)
    ancho = float(getattr(svg, "width", 0) or 0)

    tolerancia = _tolerancia_efectiva(tolerancia, max(ancho, alto), factor_mm)
    _recorrer(svg, CAPA_POR_DEFECTO, documento, alto, factor_mm, tolerancia)

    if not documento.entidades:
        documento.avisos.append(
            Aviso("aviso", "El archivo no contiene geometría reconocible.")
        )

    declaradas = [n for n in documento.capas if n != CAPA_POR_DEFECTO]
    if not declaradas:
        documento.avisos.append(
            Aviso(
                "aviso",
                "El archivo no declara capas de Inkscape; todo se ha cargado en una sola capa.",
                "Un grupo solo cuenta como capa si lleva el atributo «inkscape:groupmode».",
            )
        )

    _asignar_colores(documento)
    documento.recalcular_estadisticas()
    return documento


def _asignar_colores(documento: Documento) -> None:
    """Da a cada capa el color dominante de su contenido.

    SVG no guarda el color en la capa sino en cada elemento, de modo que sin
    esto el panel mostraría todas las capas del mismo color y el usuario
    perdería la referencia visual que trae del programa de CAD.
    """
    conteo: dict[str, dict[tuple[int, int, int], int]] = {}

    for entidad in documento.entidades:
        if entidad.color is None:
            continue
        conteo.setdefault(entidad.capa, {})
        conteo[entidad.capa][entidad.color] = conteo[entidad.capa].get(entidad.color, 0) + 1

    for nombre, colores in conteo.items():
        capa = documento.capas.get(nombre)
        if capa is None or not colores:
            continue
        dominante = max(colores.items(), key=lambda par: par[1])[0]
        # El negro sobre el fondo oscuro del visor sería invisible; se muestra
        # como blanco, que es su equivalente en pantalla dentro del CAD.
        capa.color = (255, 255, 255) if dominante == (0, 0, 0) else dominante


def _factor(ruta: RutaFS, documento: Documento) -> float | None:
    """Milímetros por píxel CSS, o ``None`` si el archivo no declara medidas.

    Solo se comprueba si el ``width`` trae una unidad física. Cuando la trae,
    `svgelements` ya ha resuelto el dibujo a píxeles y la conversión es la
    constante de 96 ppp del CSS; cuando no, las coordenadas son unidades de
    usuario sin correspondencia con ninguna medida real.
    """
    try:
        raiz = ET.parse(ruta).getroot()
    except ET.ParseError as exc:
        raise LecturaSVGError(f"«{ruta.name}» no es XML válido: {exc}") from exc

    ancho = (raiz.get("width") or "").strip()
    tiene_medida = any(ancho.endswith(u) for u in ("mm", "cm", "in", "pt", "pc"))

    if not tiene_medida:
        documento.avisos.append(
            Aviso(
                "aviso",
                "El archivo no declara medidas físicas, de modo que no tiene escala real.",
                "Se conservan las coordenadas del dibujo, pero habrá que indicar las "
                "unidades antes de exportar a DXF si importa la medida.",
            )
        )
        return None

    documento.avisos.append(
        Aviso(
            "info",
            f"El archivo declara una anchura de {ancho}; el dibujo se ha cargado en milímetros.",
        )
    )
    return MM_POR_PIXEL_CSS


def _tolerancia_efectiva(
    pedida: float, lado_mayor: float, factor_mm: float | None
) -> float:
    """Ajusta la tolerancia al tamaño del dibujo.

    La tolerancia llega expresada en unidades del modelo; se compara con el
    suelo relativo y se devuelve el mayor de los dos, de modo que un plano
    grande no se aplane con un detalle que nadie va a ver.
    """
    if lado_mayor <= 0:
        return pedida
    suelo = lado_mayor * FRACCION_TOLERANCIA
    if factor_mm:
        suelo *= factor_mm
    return max(pedida, suelo)


def _recorrer(
    nodo,
    capa: str,
    documento: Documento,
    alto: float,
    factor_mm: float | None,
    tolerancia: float,
) -> None:
    """Recorre el árbol acumulando la capa activa."""
    for hijo in nodo:
        if isinstance(hijo, Group):
            _recorrer(
                hijo,
                _capa_de(hijo, capa, documento),
                documento,
                alto,
                factor_mm,
                tolerancia,
            )
            continue

        try:
            for entidad in _convertir(hijo, capa, alto, factor_mm, tolerancia):
                documento.capa(entidad.capa)
                documento.entidades.append(entidad)
        except Exception as exc:  # noqa: BLE001 - un elemento roto no invalida el archivo
            documento.avisos.append(
                Aviso("error", f"No se ha podido interpretar un elemento {type(hijo).__name__}.", str(exc))
            )


def _capa_de(grupo: Group, capa_actual: str, documento: Documento) -> str:
    """Devuelve la capa que aporta este grupo, o la heredada si no es una capa."""
    valores = getattr(grupo, "values", {}) or {}

    modo = valores.get(f"{{{ESPACIO_INKSCAPE}}}groupmode") or valores.get(
        "inkscape:groupmode"
    )
    if modo != "layer":
        return capa_actual

    etiqueta = (
        valores.get(f"{{{ESPACIO_INKSCAPE}}}label")
        or valores.get("inkscape:label")
        or valores.get("id")
        or capa_actual
    )
    nombre = str(etiqueta)

    if nombre not in documento.capas:
        documento.capas[nombre] = Capa(nombre=nombre)

    return nombre


def _convertir(
    elemento,
    capa: str,
    alto: float,
    factor_mm: float | None,
    tolerancia: float,
) -> Iterator[Entidad]:
    """Traduce un elemento de svgelements a primitivas del modelo."""
    if isinstance(elemento, SVGText):
        texto = _texto(elemento, capa, alto, factor_mm)
        if texto is not None:
            yield texto
        return

    if not isinstance(elemento, Shape):
        return

    color = _color(elemento)
    tipo = type(elemento).__name__.upper()

    for puntos, cerrada in _poligonales(elemento, tolerancia, factor_mm):
        if len(puntos) < 2:
            continue
        yield Polilinea(
            capa=capa,
            color=color,
            tipo_origen=tipo,
            puntos=[_transformar(p, alto, factor_mm) for p in puntos],
            cerrada=cerrada,
        )


def _poligonales(
    elemento: Shape, tolerancia: float, factor_mm: float | None
) -> Iterator[tuple[list[Punto2D], bool]]:
    """Aplana una figura de SVG en una o varias poligonales.

    Todas las figuras se llevan a `Path`, que unifica rectángulos, círculos,
    elipses, líneas y polígonos, y se muestrea cada segmento según su longitud.
    """
    if isinstance(elemento, (Rect, Circle, Ellipse, SimpleLine, Polygon, Polyline)):
        camino = Path(elemento)
    elif isinstance(elemento, Path):
        camino = elemento
    else:
        return

    # La tolerancia se expresa en unidades del modelo; aquí se trabaja en las
    # coordenadas de svgelements, de modo que se deshace la conversión.
    tolerancia_usuario = tolerancia / factor_mm if factor_mm else tolerancia

    actual: list[Punto2D] = []
    for segmento in camino.segments():
        nombre = type(segmento).__name__

        if nombre == "Move":
            if len(actual) >= 2:
                yield actual, False
            actual = []
            if segmento.end is not None:
                actual.append((float(segmento.end.x), float(segmento.end.y)))
            continue

        if nombre == "Close":
            if len(actual) >= 3:
                yield actual, True
            actual = []
            continue

        if segmento.start is None or segmento.end is None:
            continue

        if not actual:
            actual.append((float(segmento.start.x), float(segmento.start.y)))

        for punto in _muestrear(segmento, nombre, tolerancia_usuario):
            actual.append(punto)

    if len(actual) >= 2:
        yield actual, False


def _muestrear(segmento, nombre: str, tolerancia: float) -> list[Punto2D]:
    """Devuelve los puntos de un segmento, sin repetir el inicial."""
    if nombre == "Line":
        return [(float(segmento.end.x), float(segmento.end.y))]

    longitud = _longitud_aproximada(segmento, nombre)

    if longitud <= 0 or tolerancia <= 0:
        n = MIN_SEGMENTOS
    else:
        # El error de una cuerda frente a su curva decrece con el cuadrado del
        # número de tramos, de modo que la raíz da los que hacen falta.
        n = math.ceil(math.sqrt(longitud / tolerancia))
        n = max(MIN_SEGMENTOS, min(n, MAX_SEGMENTOS))

    posiciones = [i / n for i in range(1, n + 1)]
    try:
        # Una sola llamada por segmento en lugar de una por punto: en los arcos,
        # cada llamada suelta rehace cálculos que se amortizan por lotes.
        muestras = segmento.npoint(posiciones)
    except Exception:  # noqa: BLE001
        muestras = [segmento.point(t) for t in posiciones]

    return [_coordenadas(p) for p in muestras]


def _coordenadas(punto) -> Punto2D:
    """Normaliza lo que devuelve svgelements a un par de números.

    Según el tipo de segmento, el muestreo por lotes entrega objetos con `.x` e
    `.y` o pares en un array de numpy. Tratarlos por igual evita perder
    justamente los arcos, que son la geometría de todo círculo y elipse.
    """
    x = getattr(punto, "x", None)
    if x is not None:
        return (float(x), float(punto.y))
    return (float(punto[0]), float(punto[1]))


def _longitud_aproximada(segmento, nombre: str) -> float:
    """Estima la longitud de un segmento sin integrarlo numéricamente.

    El método exacto de `svgelements` resuelve la integral por aproximaciones
    sucesivas y, con miles de curvas, domina por completo el tiempo de lectura:
    en un plano de excavación pasaba de medio minuto a menos de un segundo. Para
    decidir en cuántos tramos se parte una curva basta con una cota superior, y
    el polígono de control la proporciona de sobra.
    """
    try:
        if nombre == "CubicBezier":
            return (
                abs(segmento.control1 - segmento.start)
                + abs(segmento.control2 - segmento.control1)
                + abs(segmento.end - segmento.control2)
            )
        if nombre == "QuadraticBezier":
            return abs(segmento.control - segmento.start) + abs(
                segmento.end - segmento.control
            )
        if nombre == "Arc":
            # Cota generosa: el mayor de los radios por el ángulo barrido.
            radio = max(abs(float(segmento.rx)), abs(float(segmento.ry)))
            return radio * abs(float(segmento.sweep))
        return abs(segmento.end - segmento.start)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def _texto(elemento: SVGText, capa: str, alto: float, factor_mm: float | None) -> Texto | None:
    contenido = (elemento.text or "").strip()
    if not contenido:
        return None

    altura = float(getattr(elemento, "font_size", 0) or 0) or 1.0
    if factor_mm:
        altura *= factor_mm

    return Texto(
        capa=capa,
        color=_color(elemento, relleno_primero=True),
        tipo_origen="TEXT",
        contenido=contenido,
        posicion=_transformar(
            (float(elemento.x or 0), float(elemento.y or 0)), alto, factor_mm
        ),
        altura=altura,
    )


def _transformar(punto: Punto2D, alto: float, factor_mm: float | None) -> Punto2D:
    """Lleva un punto del sistema de SVG al del modelo interno.

    El eje Y se voltea respecto a la altura del documento, y la escala se aplica
    solo si el archivo permitía deducirla.
    """
    x, y = punto
    y = alto - y
    if factor_mm:
        return (x * factor_mm, y * factor_mm)
    return (x, y)


def _color(elemento, relleno_primero: bool = False) -> tuple[int, int, int] | None:
    """Extrae el color del trazo o del relleno, en ese orden."""
    orden = ("fill", "stroke") if relleno_primero else ("stroke", "fill")
    for atributo in orden:
        valor = getattr(elemento, atributo, None)
        if valor is None:
            continue
        try:
            if valor.value is None:  # «none»
                continue
            return (int(valor.red), int(valor.green), int(valor.blue))
        except (AttributeError, TypeError, ValueError):
            continue
    return None
