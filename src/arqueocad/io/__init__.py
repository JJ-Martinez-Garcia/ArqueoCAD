"""Lectores y escritores de los formatos admitidos."""

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

from .escritor_dxf import EscrituraDXFError, escribir_dxf
from .escritor_svg import EscrituraSVGError, escribir_svg
from .conversor_dwg import (
    ConversionDWGError,
    Conversor,
    SinConversor,
    convertir,
    detectar,
    version_dwg,
)
from .lector import EXTENSIONES, FormatoNoAdmitido, leer
from .lector_dxf import LecturaDXFError, leer_dxf
from .lector_svg import LecturaSVGError, leer_svg

__all__ = [
    "EXTENSIONES",
    "ConversionDWGError",
    "Conversor",
    "EscrituraDXFError",
    "EscrituraSVGError",
    "FormatoNoAdmitido",
    "SinConversor",
    "convertir",
    "detectar",
    "version_dwg",
    "LecturaDXFError",
    "LecturaSVGError",
    "escribir_dxf",
    "escribir_svg",
    "leer",
    "leer_dxf",
    "leer_svg",
]
