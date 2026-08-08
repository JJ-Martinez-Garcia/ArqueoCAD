"""Unidades de dibujo y conversión entre formatos.

La escala es el punto donde una conversión CAD se estropea de forma silenciosa:
DXF trabaja en unidades de dibujo declaradas en la cabecera (``$INSUNITS``),
mientras que SVG lo hace en píxeles y milímetros. Un plano que llega a la
publicación con la escala alterada es un error grave y difícil de detectar a
simple vista, así que aquí la correspondencia se hace explícita y comprobable
en lugar de quedar implícita.
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

from enum import IntEnum


class Unidad(IntEnum):
    """Códigos de ``$INSUNITS`` del formato DXF.

    Se recogen todos los definidos por Autodesk, aunque en la práctica solo se
    usen los métricos y los anglosajones; los restantes evitan que un archivo
    exótico se lea como «sin definir» y arrastre una escala equivocada.
    """

    SIN_DEFINIR = 0
    PULGADAS = 1
    PIES = 2
    MILLAS = 3
    MILIMETROS = 4
    CENTIMETROS = 5
    METROS = 6
    KILOMETROS = 7
    MICROPULGADAS = 8
    MILS = 9
    YARDAS = 10
    ANGSTROMS = 11
    NANOMETROS = 12
    MICRAS = 13
    DECIMETROS = 14
    DECAMETROS = 15
    HECTOMETROS = 16
    GIGAMETROS = 17
    UNIDADES_ASTRONOMICAS = 18
    ANIOS_LUZ = 19
    PARSECS = 20


#: Cuántos metros mide una unidad de cada tipo.
_A_METROS: dict[Unidad, float] = {
    Unidad.PULGADAS: 0.0254,
    Unidad.PIES: 0.3048,
    Unidad.MILLAS: 1609.344,
    Unidad.MILIMETROS: 0.001,
    Unidad.CENTIMETROS: 0.01,
    Unidad.METROS: 1.0,
    Unidad.KILOMETROS: 1000.0,
    Unidad.MICROPULGADAS: 0.0254e-6,
    Unidad.MILS: 0.0254e-3,
    Unidad.YARDAS: 0.9144,
    Unidad.ANGSTROMS: 1e-10,
    Unidad.NANOMETROS: 1e-9,
    Unidad.MICRAS: 1e-6,
    Unidad.DECIMETROS: 0.1,
    Unidad.DECAMETROS: 10.0,
    Unidad.HECTOMETROS: 100.0,
    Unidad.GIGAMETROS: 1e9,
    Unidad.UNIDADES_ASTRONOMICAS: 1.495978707e11,
    Unidad.ANIOS_LUZ: 9.4607304725808e15,
    Unidad.PARSECS: 3.0856775814913673e16,
}

_NOMBRES: dict[Unidad, str] = {
    Unidad.SIN_DEFINIR: "sin definir",
    Unidad.PULGADAS: "pulgadas",
    Unidad.PIES: "pies",
    Unidad.MILLAS: "millas",
    Unidad.MILIMETROS: "milímetros",
    Unidad.CENTIMETROS: "centímetros",
    Unidad.METROS: "metros",
    Unidad.KILOMETROS: "kilómetros",
    Unidad.MICROPULGADAS: "micropulgadas",
    Unidad.MILS: "milésimas de pulgada",
    Unidad.YARDAS: "yardas",
    Unidad.ANGSTROMS: "ångströms",
    Unidad.NANOMETROS: "nanómetros",
    Unidad.MICRAS: "micras",
    Unidad.DECIMETROS: "decímetros",
    Unidad.DECAMETROS: "decámetros",
    Unidad.HECTOMETROS: "hectómetros",
    Unidad.GIGAMETROS: "gigámetros",
    Unidad.UNIDADES_ASTRONOMICAS: "unidades astronómicas",
    Unidad.ANIOS_LUZ: "años luz",
    Unidad.PARSECS: "pársecs",
}

#: Abreviatura para la barra de estado y las mediciones.
_SIMBOLOS: dict[Unidad, str] = {
    Unidad.PULGADAS: "in",
    Unidad.PIES: "ft",
    Unidad.MILLAS: "mi",
    Unidad.MILIMETROS: "mm",
    Unidad.CENTIMETROS: "cm",
    Unidad.METROS: "m",
    Unidad.KILOMETROS: "km",
    Unidad.YARDAS: "yd",
    Unidad.DECIMETROS: "dm",
    Unidad.MICRAS: "µm",
    Unidad.NANOMETROS: "nm",
}

#: Milímetros por píxel según la convención de 96 ppp que fija el CSS y que
#: aplican tanto Inkscape (desde la versión 0.92) como los navegadores.
MM_POR_PIXEL_CSS = 25.4 / 96.0


def desde_codigo(codigo: int | None) -> Unidad:
    """Traduce ``$INSUNITS`` a `Unidad`, tolerando valores desconocidos."""
    if codigo is None:
        return Unidad.SIN_DEFINIR
    try:
        return Unidad(int(codigo))
    except ValueError:
        return Unidad.SIN_DEFINIR


def nombre(unidad: Unidad) -> str:
    return _NOMBRES.get(unidad, "sin definir")


def simbolo(unidad: Unidad) -> str:
    """Abreviatura, o ``ud.`` cuando la unidad no está definida."""
    return _SIMBOLOS.get(unidad, "ud.")


def factor_a_metros(unidad: Unidad) -> float | None:
    """Metros por unidad de dibujo.

    Devuelve ``None`` cuando la unidad no está definida. Ese caso no debe
    resolverse por omisión: hay que preguntar al usuario, porque suponer una
    escala equivocada es peor que no convertir.
    """
    return _A_METROS.get(unidad)


def factor_entre(origen: Unidad, destino: Unidad) -> float | None:
    """Factor multiplicativo para pasar de una unidad a otra."""
    f_origen = factor_a_metros(origen)
    f_destino = factor_a_metros(destino)
    if f_origen is None or f_destino is None:
        return None
    return f_origen / f_destino


def factor_a_milimetros_svg(unidad: Unidad) -> float | None:
    """Factor para exportar a SVG con las medidas reales.

    El SVG se escribe en milímetros con ``width`` y ``height`` declarados en esa
    unidad y un ``viewBox`` que conserva las coordenadas del dibujo. Así el
    archivo mantiene la escala al abrirlo en Inkscape o al imprimirlo, en lugar
    de depender del tamaño en píxeles.
    """
    factor = factor_a_metros(unidad)
    return None if factor is None else factor * 1000.0
