"""Punto único de entrada para abrir un plano.

Elige el lector según la extensión, de modo que el resto de la aplicación no
tenga que saber de formatos. Es también el sitio donde se resolverá la entrada
DWG, convirtiéndola a DXF antes de leerla.
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

from ..core.geometria import TOLERANCIA_POR_DEFECTO
from ..core.modelo import Documento

#: Extensiones admitidas, para los diálogos de apertura y el arrastrar y soltar.
EXTENSIONES = (".dxf", ".svg", ".dwg")


class FormatoNoAdmitido(Exception):
    """La extensión del archivo no corresponde a ningún formato conocido."""


def leer(ruta: str | Path, tolerancia: float = TOLERANCIA_POR_DEFECTO) -> Documento:
    """Abre un plano en cualquiera de los formatos admitidos."""
    from .lector_dxf import leer_dxf
    from .lector_svg import leer_svg

    ruta = Path(ruta)
    sufijo = ruta.suffix.casefold()

    if sufijo == ".dxf":
        return leer_dxf(ruta, tolerancia=tolerancia)

    if sufijo == ".svg":
        return leer_svg(ruta, tolerancia=tolerancia)

    if sufijo == ".dwg":
        return _leer_dwg(ruta, tolerancia)

    raise FormatoNoAdmitido(
        f"ArqueoCAD no reconoce la extensión «{ruta.suffix}».\n\n"
        "Formatos admitidos: DXF, SVG y DWG."
    )


def _leer_dwg(ruta: Path, tolerancia: float) -> Documento:
    """Convierte el DWG a DXF con un programa externo y lee el resultado.

    El documento conserva constancia de que el original era DWG y de qué archivo
    intermedio se ha leído en realidad, porque lo que se ve en pantalla es el
    resultado de una conversión y no el archivo que el usuario abrió.
    """
    from ..core.modelo import FormatoOrigen
    from .conversor_dwg import convertir
    from .lector_dxf import leer_dxf

    intermedio, avisos = convertir(ruta)

    documento = leer_dxf(intermedio, tolerancia=tolerancia)
    documento.ruta = str(ruta)
    documento.formato = FormatoOrigen.DWG
    documento.ruta_intermedia = str(intermedio)
    # Los avisos de la conversión van delante: explican qué se ha leído en
    # realidad y condicionan la lectura de los demás.
    documento.avisos[:0] = avisos

    return documento
