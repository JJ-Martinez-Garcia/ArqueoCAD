"""Pruebas del lector de SVG.

El grueso son pruebas del ciclo completo DXF → SVG → modelo: si un plano
exportado y vuelto a leer conserva capas, recuento y medidas, las dos mitades de
la conversión son coherentes entre sí.
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

import pytest

from arqueocad.core import Documento, Polilinea, Texto, Unidad
from arqueocad.io import FormatoNoAdmitido, escribir_svg, leer, leer_dxf, leer_svg

import plano_de_prueba


@pytest.fixture(scope="module")
def origen(tmp_path_factory) -> Documento:
    ruta = plano_de_prueba.construir(
        tmp_path_factory.mktemp("ciclo") / "excavacion.dxf"
    )
    return leer_dxf(ruta)


@pytest.fixture(scope="module")
def ida_y_vuelta(origen: Documento, tmp_path_factory) -> Documento:
    """El plano exportado a SVG y vuelto a leer."""
    destino = tmp_path_factory.mktemp("svg") / "ciclo.svg"
    escribir_svg(origen, origen.nombres_de_capa(), destino)
    return leer_svg(destino)


# -- despachador ---------------------------------------------------------


def test_elige_el_lector_por_la_extension(origen: Documento, tmp_path: Path) -> None:
    svg = tmp_path / "elige.svg"
    escribir_svg(origen, ["MUROS"], svg)

    assert leer(Path(origen.ruta)).formato.value == "dxf"
    assert leer(svg).formato.value == "svg"


def test_el_dwg_pasa_por_el_conversor(tmp_path: Path) -> None:
    """El despachador debe encaminar el DWG a la conversión, no rechazarlo.

    Sin conversor instalado, el error resultante es el que explica cómo
    conseguir uno; lo que no puede es tratarse como formato desconocido.
    """
    from arqueocad.io import ConversionDWGError, SinConversor

    falso = tmp_path / "plano.dwg"
    falso.write_bytes(b"AC1032" + b"\x00" * 32)

    with pytest.raises((SinConversor, ConversionDWGError)):
        leer(falso)


def test_rechaza_una_extension_desconocida(tmp_path: Path) -> None:
    otro = tmp_path / "plano.pdf"
    otro.write_bytes(b"%PDF")
    with pytest.raises(FormatoNoAdmitido):
        leer(otro)


# -- capas ---------------------------------------------------------------


def test_recupera_las_capas_de_inkscape(
    origen: Documento, ida_y_vuelta: Documento
) -> None:
    """Los nombres deben volver exactamente, tildes incluidas."""
    esperadas = {
        n for n in origen.nombres_de_capa() if origen.capas[n].n_entidades > 0
    }
    assert esperadas <= set(ida_y_vuelta.capas)


def test_un_svg_sin_capas_se_lee_como_una_sola(tmp_path: Path) -> None:
    plano = tmp_path / "plano.svg"
    plano.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="10" y="10" width="30" height="20" fill="none" stroke="#000"/>'
        "</svg>",
        encoding="utf-8",
    )

    documento = leer_svg(plano)
    assert len(documento.capas) == 1
    assert any("no declara capas" in a.mensaje for a in documento.avisos)


# -- geometría -----------------------------------------------------------


def test_no_se_pierde_geometria(origen: Documento, ida_y_vuelta: Documento) -> None:
    """La geometría vuelve entera; solo el texto puede desdoblarse.

    Un párrafo de varias líneas se escribe con un «tspan» por línea y regresa
    como un texto por cada uno. No hay pérdida, pero el recuento cambia, de modo
    que se comprueban por separado la geometría y el número de líneas.
    """
    def cuentas(documento: Documento) -> tuple[int, int]:
        geometria = sum(
            1 for e in documento.entidades if not isinstance(e, Texto)
        )
        lineas = sum(
            len(e.lineas) for e in documento.entidades if isinstance(e, Texto)
        )
        return geometria, lineas

    assert cuentas(ida_y_vuelta) == cuentas(origen)


def test_no_invierte_el_dibujo(origen: Documento, ida_y_vuelta: Documento) -> None:
    """El eje Y va al revés en SVG; sin voltearlo el plano sale del revés.

    Se compara la proporción de la envolvente, que un volteo mal hecho no
    altera, junto con la posición relativa del contenido dentro de ella.
    """
    ext_o = origen.extension()
    ext_v = ida_y_vuelta.extension()
    assert ext_v.ancho / ext_v.alto == pytest.approx(ext_o.ancho / ext_o.alto, rel=0.05)

    # El muro ocupa la mitad inferior del plano de prueba y debe seguir ahí.
    muro_o = origen.extension_de_capa("MUROS")
    muro_v = ida_y_vuelta.extension_de_capa("MUROS")
    altura_relativa_o = (muro_o.y_min - ext_o.y_min) / ext_o.alto
    altura_relativa_v = (muro_v.y_min - ext_v.y_min) / ext_v.alto
    assert altura_relativa_v == pytest.approx(altura_relativa_o, abs=0.05)


def test_conserva_la_escala(origen: Documento, ida_y_vuelta: Documento) -> None:
    """El plano está en metros y vuelve en milímetros: mil veces mayor."""
    assert ida_y_vuelta.unidad is Unidad.MILIMETROS

    ancho_o = origen.extension_de_capa("MUROS").ancho
    ancho_v = ida_y_vuelta.extension_de_capa("MUROS").ancho
    assert ancho_v == pytest.approx(ancho_o * 1000, rel=0.01)


def test_aplana_los_circulos_sin_perderlos(
    origen: Documento, ida_y_vuelta: Documento
) -> None:
    """Los círculos llegan como arcos, cuyo muestreo por lotes tiene su truco.

    `svgelements` devuelve los puntos de un arco en un array de numpy en vez de
    en objetos con `.x`, y tratarlos igual que el resto hacía desaparecer toda
    la geometría circular.
    """
    circulares = [
        e for e in ida_y_vuelta.entidades
        if isinstance(e, Polilinea) and e.capa == "UE-2" and e.cerrada
    ]
    assert circulares, "se ha perdido la geometría circular"


def test_lee_los_textos(ida_y_vuelta: Documento) -> None:
    contenidos = {
        e.contenido for e in ida_y_vuelta.entidades if isinstance(e, Texto)
    }
    assert "UE 101" in contenidos


def test_avisa_cuando_no_hay_escala_real(tmp_path: Path) -> None:
    plano = tmp_path / "sin_medidas.svg"
    plano.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="0" y="0" width="10" height="10" fill="none" stroke="#000"/>'
        "</svg>",
        encoding="utf-8",
    )

    documento = leer_svg(plano)
    assert documento.unidad is Unidad.SIN_DEFINIR
    assert any("no declara medidas" in a.mensaje for a in documento.avisos)


def test_archivo_inexistente() -> None:
    with pytest.raises(FileNotFoundError):
        leer_svg("no_existe.svg")
