"""Pruebas del recorrido SVG → DXF.

Es la única de las seis combinaciones de formatos que no pasa por un documento
de ezdxf de origen, de modo que necesita su propio camino en el escritor. Sin
ella, el encargo quedaba a medias: se puede entrar por SVG pero no salir a DXF.
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

import ezdxf
import pytest

from arqueocad.core import Documento, Formato, Opciones, Unidad, separar
from arqueocad.io import escribir_dxf, escribir_svg, leer_dxf, leer_svg

import plano_de_prueba


@pytest.fixture(scope="module")
def desde_svg(tmp_path_factory) -> Documento:
    """El plano de prueba pasado a SVG y vuelto a leer."""
    carpeta = tmp_path_factory.mktemp("svg_a_dxf")
    origen = leer_dxf(plano_de_prueba.construir(carpeta / "origen.dxf"))
    svg = carpeta / "intermedio.svg"
    escribir_svg(origen, origen.nombres_de_capa(), svg)
    return leer_svg(svg)


def test_un_svg_puede_exportarse_a_dxf(desde_svg: Documento, tmp_path: Path) -> None:
    destino = tmp_path / "desde_svg.dxf"
    escribir_dxf(desde_svg, ["MUROS"], destino)

    assert destino.is_file()
    assert destino.stat().st_size > 0


def test_no_necesita_documento_de_origen(desde_svg: Documento) -> None:
    """Un plano leído de SVG no trae documento de ezdxf, y debe exportarse igual."""
    assert desde_svg.origen_ezdxf is None


def test_avisa_de_que_se_genera_desde_la_geometria(
    desde_svg: Documento, tmp_path: Path
) -> None:
    avisos = escribir_dxf(desde_svg, ["MUROS"], tmp_path / "aviso.dxf")
    assert any("a partir de la geometría" in a.mensaje for a in avisos)


def test_conserva_las_capas(desde_svg: Documento, tmp_path: Path) -> None:
    destino = tmp_path / "capas.dxf"
    escribir_dxf(desde_svg, ["MUROS", "UE-2"], destino)

    devuelto = leer_dxf(destino)
    con_contenido = {n for n, c in devuelto.capas.items() if c.n_entidades > 0}
    assert con_contenido == {"MUROS", "UE-2"}


def test_conserva_la_geometria(desde_svg: Documento, tmp_path: Path) -> None:
    """La envolvente debe sobrevivir al viaje completo DXF → SVG → DXF."""
    destino = tmp_path / "geometria.dxf"
    escribir_dxf(desde_svg, ["MUROS"], destino)

    antes = desde_svg.extension_de_capa("MUROS")
    despues = leer_dxf(destino).extension_de_capa("MUROS")

    assert despues.ancho == pytest.approx(antes.ancho, rel=1e-4)
    assert despues.alto == pytest.approx(antes.alto, rel=1e-4)


def test_conserva_las_unidades(desde_svg: Documento, tmp_path: Path) -> None:
    """El SVG llegó en milímetros y el DXF debe declararlo."""
    destino = tmp_path / "unidades.dxf"
    escribir_dxf(desde_svg, ["MUROS"], destino)
    assert leer_dxf(destino).unidad is Unidad.MILIMETROS


def test_escribe_entidades_nativas(desde_svg: Documento, tmp_path: Path) -> None:
    """No basta con que el archivo exista: tiene que llevar geometría de CAD."""
    destino = tmp_path / "entidades.dxf"
    escribir_dxf(desde_svg, ["MUROS", "TEXTOS"], destino)

    tipos = {e.dxftype() for e in ezdxf.readfile(destino).modelspace()}
    assert "LWPOLYLINE" in tipos
    assert tipos & {"TEXT", "MTEXT"}


def test_la_separacion_completa_funciona_desde_svg(
    desde_svg: Documento, tmp_path: Path
) -> None:
    """El caso real: abrir un SVG y separarlo en un DXF por capa."""
    resultado = separar(
        desde_svg,
        desde_svg.nombres_de_capa(),
        Opciones(carpeta=tmp_path, formatos=(Formato.DXF,)),
    )

    assert resultado.total_archivos > 0
    assert not resultado.hubo_problemas
    for archivo in resultado.archivos:
        assert archivo.ruta.is_file()
        leer_dxf(archivo.ruta)  # debe poder releerse sin error
