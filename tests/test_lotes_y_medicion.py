"""Pruebas del proceso por lotes y de la medición."""

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
from pathlib import Path

import pytest

from arqueocad.core import (
    Documento,
    Formato,
    Opciones,
    OpcionesLote,
    Unidad,
    capas_que_encajan,
    procesar_lote,
)
from arqueocad.core.medicion import Medicion
from arqueocad.io import leer_dxf

import plano_de_prueba


@pytest.fixture(scope="module")
def documento(tmp_path_factory) -> Documento:
    ruta = plano_de_prueba.construir(
        tmp_path_factory.mktemp("lote") / "excavacion.dxf"
    )
    return leer_dxf(ruta)


@pytest.fixture
def campaña(tmp_path: Path) -> list[Path]:
    """Tres planos como los de una campaña, con la misma nomenclatura."""
    carpeta = tmp_path / "campaña"
    carpeta.mkdir()
    return [
        plano_de_prueba.construir(carpeta / f"sector_{n}.dxf") for n in (1, 2, 3)
    ]


# -- filtro de capas -----------------------------------------------------


def test_sin_patrones_entran_todas(documento: Documento) -> None:
    assert capas_que_encajan(documento, []) == documento.nombres_de_capa()


def test_filtra_por_comodin(documento: Documento) -> None:
    assert capas_que_encajan(documento, ["UE-*"]) == ["UE-2", "UE-10", "UE-101"]


def test_admite_varios_patrones(documento: Documento) -> None:
    encajan = capas_que_encajan(documento, ["MURO*", "COTAS"])
    assert set(encajan) == {"MUROS", "COTAS"}


def test_el_filtro_ignora_mayusculas(documento: Documento) -> None:
    """La nomenclatura de campo rara vez es constante en ese punto."""
    assert capas_que_encajan(documento, ["muros"]) == ["MUROS"]


def test_filtra_por_sufijo_de_campaña(documento: Documento) -> None:
    assert capas_que_encajan(documento, ["*-101"]) == ["UE-101"]


# -- proceso por lotes ---------------------------------------------------


def test_procesa_todos_los_planos(campaña: list[Path], tmp_path: Path) -> None:
    salida = tmp_path / "salida"
    resultado = procesar_lote(
        campaña,
        OpcionesLote(separacion=Opciones(carpeta=salida, formatos=(Formato.DXF,))),
    )

    assert len(resultado.correctos) == 3
    assert not resultado.fallidos
    assert resultado.total_archivos > 0


def test_una_subcarpeta_por_plano(campaña: list[Path], tmp_path: Path) -> None:
    salida = tmp_path / "salida"
    procesar_lote(
        campaña,
        OpcionesLote(
            separacion=Opciones(carpeta=salida), subcarpeta_por_plano=True
        ),
    )

    subcarpetas = {p.name for p in salida.iterdir() if p.is_dir()}
    assert subcarpetas == {"sector_1", "sector_2", "sector_3"}


def test_sin_subcarpetas_los_nombres_no_colisionan(
    campaña: list[Path], tmp_path: Path
) -> None:
    """Compartiendo carpeta, el prefijo de cada plano evita que se pisen."""
    salida = tmp_path / "juntos"
    resultado = procesar_lote(
        campaña,
        OpcionesLote(
            separacion=Opciones(carpeta=salida), subcarpeta_por_plano=False
        ),
    )

    generados = [a.ruta.name for p in resultado.correctos for a in p.archivos]
    assert len(generados) == len(set(generados)), "hay archivos que se pisan"
    assert any(n.startswith("sector_1_") for n in generados)
    assert any(n.startswith("sector_3_") for n in generados)


def test_aplica_el_filtro_a_todo_el_lote(campaña: list[Path], tmp_path: Path) -> None:
    salida = tmp_path / "solo_ue"
    resultado = procesar_lote(
        campaña,
        OpcionesLote(
            separacion=Opciones(carpeta=salida), patrones=["UE-*"]
        ),
    )

    for plano in resultado.correctos:
        assert plano.n_capas == 3
        for archivo in plano.archivos:
            assert "UE-" in archivo.ruta.stem


def test_un_plano_roto_no_detiene_la_campaña(
    campaña: list[Path], tmp_path: Path
) -> None:
    """Con veinte planos, uno defectuoso no puede echar por tierra el trabajo."""
    roto = tmp_path / "campaña" / "corrupto.dxf"
    roto.write_text("esto no es un DXF", encoding="utf-8")

    resultado = procesar_lote(
        [campaña[0], roto, campaña[1]],
        OpcionesLote(separacion=Opciones(carpeta=tmp_path / "salida")),
    )

    assert len(resultado.correctos) == 2
    assert len(resultado.fallidos) == 1
    assert resultado.fallidos[0].ruta.name == "corrupto.dxf"
    assert resultado.fallidos[0].error


def test_informa_del_avance(campaña: list[Path], tmp_path: Path) -> None:
    llamadas: list[tuple[int, int]] = []
    procesar_lote(
        campaña,
        OpcionesLote(separacion=Opciones(carpeta=tmp_path / "salida")),
        progreso=lambda h, t, _: llamadas.append((h, t)),
    )
    assert llamadas[-1] == (3, 3)


def test_puede_cancelarse(campaña: list[Path], tmp_path: Path) -> None:
    """Un lote largo debe poder interrumpirse sin dejar la aplicación colgada."""
    resultado = procesar_lote(
        campaña,
        OpcionesLote(separacion=Opciones(carpeta=tmp_path / "salida")),
        cancelado=lambda: True,
    )
    assert not resultado.planos


# -- medición ------------------------------------------------------------


def test_mide_una_distancia() -> None:
    medicion = Medicion(unidad=Unidad.METROS)
    medicion.anadir((0.0, 0.0))
    medicion.anadir((3.0, 4.0))
    assert medicion.longitud == pytest.approx(5.0)
    assert "5" in medicion.texto_longitud()


def test_suma_los_tramos() -> None:
    medicion = Medicion(unidad=Unidad.METROS)
    for punto in [(0.0, 0.0), (3.0, 0.0), (3.0, 4.0)]:
        medicion.anadir(punto)
    assert medicion.longitud == pytest.approx(7.0)
    assert medicion.ultimo_tramo == pytest.approx(4.0)


def test_mide_una_superficie() -> None:
    medicion = Medicion(unidad=Unidad.METROS)
    for punto in [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]:
        medicion.anadir(punto)
    assert medicion.area == pytest.approx(12.0)
    assert medicion.perimetro == pytest.approx(14.0)


def test_el_area_no_depende_del_sentido() -> None:
    horario = Medicion()
    antihorario = Medicion()
    puntos = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    for punto in puntos:
        horario.anadir(punto)
    for punto in reversed(puntos):
        antihorario.anadir(punto)
    assert horario.area == pytest.approx(antihorario.area)


def test_el_acimut_se_mide_desde_el_norte() -> None:
    """Convención topográfica: 0° al norte y creciendo hacia el este."""
    norte = Medicion()
    norte.anadir((0.0, 0.0))
    norte.anadir((0.0, 10.0))
    assert norte.acimut == pytest.approx(0.0)

    este = Medicion()
    este.anadir((0.0, 0.0))
    este.anadir((10.0, 0.0))
    assert este.acimut == pytest.approx(90.0)

    sur = Medicion()
    sur.anadir((0.0, 0.0))
    sur.anadir((0.0, -10.0))
    assert sur.acimut == pytest.approx(180.0)


def test_elige_el_multiplo_legible() -> None:
    medicion = Medicion(unidad=Unidad.METROS)
    medicion.anadir((0.0, 0.0))
    medicion.anadir((0.0, 0.05))
    assert "cm" in medicion.texto_longitud()

    lejos = Medicion(unidad=Unidad.METROS)
    lejos.anadir((0.0, 0.0))
    lejos.anadir((0.0, 2500.0))
    assert "km" in lejos.texto_longitud()


def test_sin_unidades_no_se_inventa_la_medida() -> None:
    """Dar «12,4 m» sobre un plano de escala desconocida sería inventar un dato."""
    medicion = Medicion(unidad=Unidad.SIN_DEFINIR)
    medicion.anadir((0.0, 0.0))
    medicion.anadir((3.0, 4.0))
    texto = medicion.texto_longitud()
    assert "ud." in texto
    assert " m" not in texto


def test_deshacer_y_limpiar() -> None:
    medicion = Medicion()
    medicion.anadir((0.0, 0.0))
    medicion.anadir((1.0, 1.0))
    medicion.deshacer()
    assert len(medicion.puntos) == 1
    medicion.limpiar()
    assert not medicion.activa


def test_el_resumen_guia_al_principio() -> None:
    medicion = Medicion(unidad=Unidad.METROS)
    assert "primer punto" in medicion.resumen()
    medicion.anadir((0.0, 0.0))
    assert "segundo punto" in medicion.resumen()
    medicion.anadir((3.0, 4.0))
    assert "Longitud" in medicion.resumen()
    medicion.anadir((0.0, 4.0))
    assert "Área" in medicion.resumen()
