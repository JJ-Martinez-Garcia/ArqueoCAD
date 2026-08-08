"""Modelo interno neutro, geometría y unidades."""

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

from .modelo import (
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
from .geometria import Extension, Punto2D, TOLERANCIA_POR_DEFECTO
from .lotes import (
    OpcionesLote,
    ResultadoLote,
    ResultadoPlano,
    capas_que_encajan,
    procesar_lote,
)
from .separador import (
    ArchivoGenerado,
    Formato,
    Modo,
    Opciones,
    Resultado,
    separar,
)
from .unidades import Unidad

__all__ = [
    "ArchivoGenerado",
    "Aviso",
    "Capa",
    "Documento",
    "Entidad",
    "Extension",
    "Formato",
    "FormatoOrigen",
    "Modo",
    "Opciones",
    "OpcionesLote",
    "Resultado",
    "ResultadoLote",
    "ResultadoPlano",
    "capas_que_encajan",
    "procesar_lote",
    "separar",
    "Polilinea",
    "Punto",
    "Punto2D",
    "Relleno",
    "TOLERANCIA_POR_DEFECTO",
    "Texto",
    "Unidad",
]
