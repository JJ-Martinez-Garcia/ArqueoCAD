"""Escritura de SVG con capas reconocibles por Inkscape.

Un SVG «con capas» no es un SVG con grupos: Inkscape e Illustrator solo tratan
un grupo como capa si lleva el atributo ``inkscape:groupmode="layer"`` y su
etiqueta. Sin eso, el archivo se abre como un amasijo de trazos y hay que
rehacer a mano la separación que la aplicación acaba de calcular.

Sobre la escala. El archivo declara ``width`` y ``height`` en milímetros reales
y un ``viewBox`` que conserva las proporciones del dibujo, de modo que las
medidas se mantienen al abrirlo o al imprimirlo. Con `escala` puede pedirse una
reducción de publicación: `escala=50` produce un dibujo a 1:50.
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

from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape, quoteattr

from ..core.geometria import Extension
from ..core.modelo import (
    Aviso,
    Documento,
    Entidad,
    Polilinea,
    Punto,
    Relleno,
    Texto,
)
from ..core.unidades import Unidad, factor_a_milimetros_svg

#: Grosor de trazo por defecto, como fracción del lado mayor del dibujo. Da una
#: línea fina pero visible sea cual sea la unidad del plano, que es lo que no
#: consigue un valor fijo: 0,1 sirve en milímetros y desaparece en metros.
FRACCION_GROSOR = 1 / 2000

#: Radio con que se dibujan las entidades POINT, en la misma proporción.
FRACCION_RADIO_PUNTO = 1 / 500

#: Decimales de las coordenadas. Seis bastan para la precisión topográfica y
#: evitan archivos inflados con ruido de coma flotante.
DECIMALES = 6

#: El color 7 de AutoCAD se dibuja blanco sobre el fondo negro del programa,
#: pero se imprime **negro** sobre papel. Sin esta conversión, el cajetín, el
#: marco y buena parte de la rotulación desaparecen al abrir el SVG en Inkscape,
#: que trabaja sobre fondo blanco.
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)


class EscrituraSVGError(Exception):
    """El archivo de salida no ha podido generarse."""


def escribir_svg(
    documento: Documento,
    capas: Iterable[str],
    destino: str | Path,
    escala: float = 1.0,
    unidad_forzada: Unidad | None = None,
    grosor: float | None = None,
    colores_para_papel: bool = True,
) -> list[Aviso]:
    """Escribe un SVG con las capas indicadas, cada una como capa de Inkscape.

    Args:
        documento: plano de partida.
        capas: nombres de las capas que se incluyen, en el orden de apilado.
        destino: archivo a crear.
        escala: denominador de la escala de salida (50 produce un 1:50).
        unidad_forzada: unidad que se aplica cuando el plano no la declara.
        grosor: grosor de trazo en unidades de dibujo; si se omite, se deduce
            del tamaño del plano.
        colores_para_papel: convierte el blanco en negro, como hace AutoCAD al
            imprimir. Desactivarlo conserva los colores de pantalla, útil solo
            si el SVG se va a componer sobre un fondo oscuro.

    Returns:
        Avisos de lo que se ha simplificado o quedado fuera.
    """
    seleccion = [c for c in capas]
    if not seleccion:
        raise EscrituraSVGError("No se ha seleccionado ninguna capa.")

    avisos: list[Aviso] = []
    entidades = documento.entidades_de(seleccion)
    extension = Extension.union(e.extension() for e in entidades)

    if extension.vacia:
        raise EscrituraSVGError(
            "Las capas seleccionadas no contienen geometría que exportar."
        )

    lado_mayor = max(extension.ancho, extension.alto, 1e-9)
    if grosor is None:
        grosor = lado_mayor * FRACCION_GROSOR
    radio_punto = lado_mayor * FRACCION_RADIO_PUNTO

    unidad = unidad_forzada if unidad_forzada is not None else documento.unidad
    cabecera = _cabecera(extension, unidad, escala, avisos)

    lineas = [cabecera]
    # El grupo raíz invierte el eje Y y traslada el origen a la esquina del
    # dibujo, de modo que dentro se pueda escribir en coordenadas del plano.
    lineas.append(
        f'<g transform="translate({_n(-extension.x_min)},{_n(extension.y_max)}) scale(1,-1)">'
    )

    por_capa: dict[str, list[Entidad]] = {nombre: [] for nombre in seleccion}
    for entidad in entidades:
        por_capa.setdefault(entidad.capa, []).append(entidad)

    sustituciones_fuente = 0
    patrones_perdidos = 0

    for indice, nombre in enumerate(seleccion, start=1):
        capa = documento.capas.get(nombre)
        color_capa = _hex(capa.color if capa else NEGRO, colores_para_papel)

        # La capa se escribe siempre visible. Que estuviera apagada o congelada
        # en el archivo de origen no significa que no deba exportarse: si el
        # usuario la ha seleccionado, la quiere en el resultado.
        lineas.append(
            f'<g inkscape:groupmode="layer" inkscape:label={quoteattr(nombre)} '
            f'id="capa{indice}" style="display:inline">'
        )

        for entidad in por_capa.get(nombre, []):
            color = (
                _hex(entidad.color, colores_para_papel)
                if entidad.color
                else color_capa
            )
            if isinstance(entidad, Polilinea):
                lineas.append(_polilinea(entidad, color, grosor))
            elif isinstance(entidad, Relleno):
                lineas.append(_relleno(entidad, color, grosor))
                if not entidad.solido and entidad.patron:
                    patrones_perdidos += 1
            elif isinstance(entidad, Punto):
                lineas.append(_punto(entidad, color, radio_punto))
            elif isinstance(entidad, Texto):
                lineas.append(_texto(entidad, color))
                sustituciones_fuente += 1

        lineas.append("</g>")

    lineas.append("</g>")
    lineas.append("</svg>")

    if sustituciones_fuente:
        avisos.append(
            Aviso(
                "aviso",
                f"{sustituciones_fuente} textos se han escrito con una fuente genérica.",
                "SVG no admite las fuentes vectoriales de AutoCAD; conviene revisar "
                "el aspecto de los rótulos en Inkscape.",
            )
        )
    if patrones_perdidos:
        avisos.append(
            Aviso(
                "aviso",
                f"{patrones_perdidos} sombreados han conservado solo su contorno.",
                "Los patrones de relleno de AutoCAD no tienen equivalente en SVG.",
            )
        )

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    except IOError as exc:
        raise EscrituraSVGError(f"No se puede escribir «{destino.name}»: {exc}") from exc

    return avisos


def _cabecera(
    extension: Extension, unidad: Unidad, escala: float, avisos: list[Aviso]
) -> str:
    """Construye la etiqueta ``<svg>`` con sus medidas físicas."""
    ancho = extension.ancho
    alto = extension.alto
    factor = factor_a_milimetros_svg(unidad)

    medidas = ""
    if factor is None:
        avisos.append(
            Aviso(
                "aviso",
                "El plano no declara sus unidades, de modo que el SVG no lleva medidas físicas.",
                "Conserva las proporciones, pero al imprimirlo habrá que fijar la escala a mano.",
            )
        )
    else:
        if escala <= 0:
            escala = 1.0
        medidas = (
            f' width="{_n(ancho * factor / escala)}mm"'
            f' height="{_n(alto * factor / escala)}mm"'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"'
        f'{medidas} viewBox="0 0 {_n(ancho)} {_n(alto)}" version="1.1">'
    )


def _polilinea(entidad: Polilinea, color: str, grosor: float) -> str:
    if len(entidad.puntos) < 2:
        return ""
    return (
        f'<path d="{_trazado(entidad.puntos, entidad.cerrada)}" fill="none" '
        f'stroke="{color}" stroke-width="{_n(grosor)}" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
    )


def _relleno(entidad: Relleno, color: str, grosor: float) -> str:
    trazados = [_trazado(c, True) for c in entidad.contornos if len(c) >= 3]
    if not trazados:
        return ""
    relleno = f'fill="{color}" fill-opacity="0.35" fill-rule="evenodd"' if entidad.solido else 'fill="none"'
    return (
        f'<path d="{" ".join(trazados)}" {relleno} '
        f'stroke="{color}" stroke-width="{_n(grosor)}"/>'
    )


def _punto(entidad: Punto, color: str, radio: float) -> str:
    x, y = entidad.posicion
    return f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(radio)}" fill="{color}"/>'


def _texto(entidad: Texto, color: str) -> str:
    """Escribe el texto compensando la inversión del eje Y.

    Sin la inversión local el rótulo saldría en espejo, porque el grupo raíz
    tiene el eje Y volteado.
    """
    x, y = entidad.posicion
    giro = f" rotate({_n(-entidad.rotacion)})" if entidad.rotacion else ""
    transformacion = f"translate({_n(x)},{_n(y)}) scale(1,-1){giro}"

    partes = [
        f'<text transform="{transformacion}" fill="{color}" '
        f'font-size="{_n(entidad.altura)}" font-family="sans-serif" '
        'dominant-baseline="alphabetic">'
    ]
    salto = entidad.altura * entidad.interlineado
    for indice, linea in enumerate(entidad.lineas):
        desplazamiento = f' x="0" dy="{_n(salto if indice else 0)}"'
        partes.append(f"<tspan{desplazamiento}>{escape(linea)}</tspan>")
    partes.append("</text>")
    return "".join(partes)


def _trazado(puntos, cerrado: bool) -> str:
    """Genera el atributo ``d`` de un ``<path>``."""
    if not puntos:
        return ""
    orden = [f"M {_n(puntos[0][0])} {_n(puntos[0][1])}"]
    orden.extend(f"L {_n(x)} {_n(y)}" for x, y in puntos[1:])
    if cerrado:
        orden.append("Z")
    return " ".join(orden)


def _hex(rgb: tuple[int, int, int], para_papel: bool = True) -> str:
    """Traduce el color a notación hexadecimal, invirtiendo el blanco si procede."""
    if para_papel and tuple(rgb) == BLANCO:
        rgb = NEGRO
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _n(valor: float) -> str:
    """Formatea un número sin ceros ni puntos sobrantes."""
    texto = f"{valor:.{DECIMALES}f}".rstrip("0").rstrip(".")
    return texto if texto not in ("", "-") else "0"
