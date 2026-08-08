"""Pruebas del lector de DXF."""

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

import pytest

from arqueocad.core import Documento, Polilinea, Punto, Relleno, Texto, Unidad
from arqueocad.io import leer_dxf

import plano_de_prueba


@pytest.fixture(scope="module")
def documento(tmp_path_factory) -> Documento:
    ruta = plano_de_prueba.construir(
        tmp_path_factory.mktemp("planos") / "excavacion.dxf"
    )
    return leer_dxf(ruta)


def test_lee_las_unidades(documento: Documento) -> None:
    assert documento.unidad is Unidad.METROS


def test_lee_todas_las_capas(documento: Documento) -> None:
    for nombre in plano_de_prueba.CAPAS:
        assert nombre in documento.capas


def test_ordena_las_capas_de_forma_natural(documento: Documento) -> None:
    nombres = [n for n in documento.nombres_de_capa() if n.startswith("UE-")]
    assert nombres == ["UE-2", "UE-10", "UE-101"]


def test_resuelve_el_color_de_capa_a_rgb(documento: Documento) -> None:
    # El ACI 1 es rojo puro en la tabla de AutoCAD.
    assert documento.capas["UE-2"].color == (255, 0, 0)


def test_convierte_cada_tipo_de_entidad(documento: Documento) -> None:
    tipos = {e.tipo_origen for e in documento.entidades}
    for esperado in ("LWPOLYLINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE", "LINE"):
        assert esperado in tipos, f"falta {esperado}"


def test_aplana_las_curvas(documento: Documento) -> None:
    """Un círculo de radio 1,2 debe llegar como poligonal cerrada y densa."""
    circulos = [
        e for e in documento.entidades
        if isinstance(e, Polilinea) and e.tipo_origen == "CIRCLE"
    ]
    assert circulos, "no se ha leído ningún círculo"
    circulo = circulos[0]
    assert circulo.cerrada
    assert len(circulo.puntos) > 50, "el aplanado es demasiado grosero"

    # Todos los vértices deben caer sobre la circunferencia original.
    for x, y in circulo.puntos:
        assert math.isclose(math.hypot(x - 3, y - 2), 1.2, rel_tol=1e-3)


def test_lee_los_textos(documento: Documento) -> None:
    contenidos = {e.contenido for e in documento.entidades if isinstance(e, Texto)}
    assert "UE 101" in contenidos
    assert any("Sector A" in c for c in contenidos)


def test_conserva_los_saltos_de_linea_del_mtext(documento: Documento) -> None:
    """Un párrafo de MTEXT no debe llegar con las líneas concatenadas.

    Sin esto se obtienen rótulos del tipo «Sector ACampaña 2026», que es lo que
    ocurre al descartar los códigos «\\P» del formato.
    """
    parrafos = [
        e for e in documento.entidades
        if isinstance(e, Texto) and e.tipo_origen == "MTEXT"
    ]
    assert parrafos, "no se ha leído el MTEXT"
    parrafo = parrafos[0]
    assert parrafo.multilinea
    assert parrafo.lineas == ["Sector A", "Campaña 2026"]


def test_la_extension_del_parrafo_crece_hacia_abajo(documento: Documento) -> None:
    """Las líneas siguientes se escriben por debajo del punto de inserción."""
    parrafo = next(
        e for e in documento.entidades
        if isinstance(e, Texto) and e.tipo_origen == "MTEXT"
    )
    ext = parrafo.extension()
    assert ext.y_min < parrafo.posicion[1]
    assert ext.alto > parrafo.altura


def test_lee_los_puntos_de_cota(documento: Documento) -> None:
    puntos = [
        e for e in documento.entidades if isinstance(e, Punto) and e.capa == "COTAS"
    ]
    assert len(puntos) == 3


def test_marca_defpoints_como_no_imprimible(documento: Documento) -> None:
    """La acotación crea puntos de definición que no forman parte del dibujo.

    AutoCAD los deposita en «Defpoints» y nunca los imprime; deben quedar
    excluidos de la exportación por defecto.
    """
    defpoints = documento.capas.get("Defpoints")
    assert defpoints is not None, "la cota debería haber creado la capa Defpoints"
    assert not defpoints.imprimible
    assert defpoints.auxiliar


def test_lee_los_sombreados_y_solidos(documento: Documento) -> None:
    rellenos = [e for e in documento.entidades if isinstance(e, Relleno)]
    tipos = {r.tipo_origen for r in rellenos}
    assert "HATCH" in tipos
    assert "SOLID" in tipos


def test_el_solido_no_se_cruza_en_reloj_de_arena(documento: Documento) -> None:
    """Comprueba el reordenado de vértices propio de SOLID.

    Con el orden que trae el formato, el contorno se cruzaría sobre sí mismo y
    el área encerrada saldría nula.
    """
    solidos = [
        e for e in documento.entidades
        if isinstance(e, Relleno) and e.tipo_origen == "SOLID"
    ]
    assert solidos
    assert _area(solidos[0].contornos[0]) == pytest.approx(1.0, rel=1e-6)


def test_despliega_las_cotas(documento: Documento) -> None:
    assert any(e.capa == "COTAS" and isinstance(e, Polilinea) for e in documento.entidades)


def test_el_bloque_hereda_la_capa_de_insercion(documento: Documento) -> None:
    """La geometría del bloque en la capa «0» debe adoptar la capa donde se inserta.

    El bloque NORTE se inserta dos veces, en TEXTOS y en MUROS; sus tres líneas
    están dibujadas en la capa «0» y ninguna debe quedarse allí.
    """
    en_capa_cero = [e for e in documento.entidades if e.capa == "0"]
    assert not en_capa_cero, "hay geometría de bloque abandonada en la capa 0"


def test_el_bloque_conserva_sus_capas_propias(documento: Documento) -> None:
    """El círculo del bloque está en UE-101 y debe seguir estándolo."""
    circulos = [
        e for e in documento.entidades
        if e.tipo_origen == "CIRCLE" and e.capa == "UE-101"
    ]
    assert len(circulos) == 2, "una por cada inserción del bloque"


def test_aplica_la_transformacion_de_insercion(documento: Documento) -> None:
    """La segunda inserción va a escala 0,5, y el radio debe reflejarlo."""
    radios = sorted(
        _radio_aproximado(e.puntos)
        for e in documento.entidades
        if e.tipo_origen == "CIRCLE" and e.capa == "UE-101"
    )
    assert radios[0] == pytest.approx(0.075, rel=1e-2)
    assert radios[1] == pytest.approx(0.15, rel=1e-2)


def test_calcula_la_extension(documento: Documento) -> None:
    ext = documento.extension()
    assert not ext.vacia
    assert ext.x_min <= 0 and ext.x_max >= 10


def test_cuenta_entidades_por_capa(documento: Documento) -> None:
    assert documento.capas["MUROS"].n_entidades > 0
    assert "LWPOLYLINE" in documento.capas["MUROS"].tipos_presentes


def test_conserva_el_documento_de_origen(documento: Documento) -> None:
    """Es la fuente de verdad para exportar a DXF sin pérdida."""
    assert documento.origen_ezdxf is not None


def test_archivo_inexistente() -> None:
    with pytest.raises(FileNotFoundError):
        leer_dxf("no_existe.dxf")


def _area(puntos) -> float:
    """Área por la fórmula del cordón de zapato, en valor absoluto."""
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x0, y0 = puntos[i]
        x1, y1 = puntos[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2


def _radio_aproximado(puntos) -> float:
    cx = sum(p[0] for p in puntos) / len(puntos)
    cy = sum(p[1] for p in puntos) / len(puntos)
    return sum(math.hypot(x - cx, y - cy) for x, y in puntos) / len(puntos)
