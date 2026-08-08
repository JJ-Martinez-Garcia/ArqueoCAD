"""Pruebas de la vectorización de imágenes.

Se construyen dibujos sintéticos de geometría conocida, de modo que el resultado
pueda contrastarse con una verdad de referencia. Es la única forma de detectar
errores que no rompen nada visible: un plano transpuesto, o una recta troceada
en cientos de fragmentos, parecen correctos hasta que se miden.
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

import numpy as np
import pytest

from arqueocad.core import Polilinea
from arqueocad.core.modelo import FormatoOrigen
from arqueocad.core.unidades import Unidad
from arqueocad.io import escribir_dxf, escribir_svg, leer_dxf
from arqueocad.io.lector import es_imagen
from arqueocad.io.vectorizador import (
    EstrategiaCapas,
    OpcionesVectorizado,
    VectorizacionError,
    calcular_escala,
    vectorizar,
)

cv2 = pytest.importorskip("cv2", reason="OpenCV no está instalado")


@pytest.fixture
def rectangulo(tmp_path: Path) -> Path:
    """Un rectángulo de 400 × 200 px con el trazo fino, sobre fondo blanco."""
    img = np.full((400, 700, 3), 255, np.uint8)
    cv2.rectangle(img, (100, 100), (500, 300), (0, 0, 0), 2)
    ruta = tmp_path / "rectangulo.png"
    cv2.imwrite(str(ruta), img)
    return ruta


@pytest.fixture
def dos_grosores(tmp_path: Path) -> Path:
    """Dos líneas, una fina y otra gruesa, para la separación por grosor."""
    img = np.full((300, 600, 3), 255, np.uint8)
    cv2.line(img, (50, 100), (550, 100), (0, 0, 0), 2)
    cv2.line(img, (50, 200), (550, 200), (0, 0, 0), 9)
    ruta = tmp_path / "grosores.png"
    cv2.imwrite(str(ruta), img)
    return ruta


# -- reconocimiento de formato ------------------------------------------


def test_reconoce_las_extensiones_de_imagen() -> None:
    assert es_imagen("plano.jpg")
    assert es_imagen("PLANO.PNG")
    assert es_imagen("escaneo.tiff")
    assert not es_imagen("plano.dxf")


def test_una_imagen_no_se_abre_como_plano(rectangulo: Path) -> None:
    """Debe remitir al diálogo, no tratarse como formato desconocido."""
    from arqueocad.io import FormatoNoAdmitido, leer

    with pytest.raises(FormatoNoAdmitido, match="Vectorizar"):
        leer(rectangulo)


def test_un_archivo_que_no_es_imagen(tmp_path: Path) -> None:
    falso = tmp_path / "roto.png"
    falso.write_text("esto no es una imagen", encoding="utf-8")
    with pytest.raises(VectorizacionError):
        vectorizar(falso)


# -- geometría -----------------------------------------------------------


def test_recupera_la_geometria(rectangulo: Path) -> None:
    resultado = vectorizar(rectangulo, OpcionesVectorizado(tolerancia=1.0))

    assert resultado.n_trazos > 0
    assert resultado.documento.formato is FormatoOrigen.RASTER
    assert all(isinstance(e, Polilinea) for e in resultado.documento.entidades)


def test_no_trocea_las_rectas(rectangulo: Path) -> None:
    """Un rectángulo son cuatro lados, no cientos de fragmentos.

    El adelgazamiento deja píxeles con tres vecinos en cada escalón diagonal, y
    si se toman por bifurcaciones una recta larga acaba partida en trozos de dos
    píxeles.
    """
    resultado = vectorizar(rectangulo, OpcionesVectorizado(tolerancia=1.0))

    assert resultado.n_trazos <= 8, "el trazo se ha fragmentado"
    assert resultado.n_descartados == 0, "se han descartado fragmentos espurios"


def test_no_transpone_el_dibujo(rectangulo: Path) -> None:
    """El rectángulo es más ancho que alto y debe seguir siéndolo.

    Las coordenadas de una imagen llegan en (fila, columna); tratarlas como
    (x, y) gira el plano entero sin que nada falle de forma visible.
    """
    resultado = vectorizar(rectangulo, OpcionesVectorizado(tolerancia=1.0))
    extension = resultado.documento.extension()

    assert extension.ancho > extension.alto
    assert extension.ancho == pytest.approx(400, abs=6)
    assert extension.alto == pytest.approx(200, abs=6)


def test_sigue_la_linea_central_y_no_los_bordes(tmp_path: Path) -> None:
    """Una línea debe dar un trazo, no dos paralelos.

    Vectorizar por contornos devuelve los dos bordes de cada trazo, que es el
    error clásico: el dibujo parece correcto pero cada línea está duplicada.
    """
    img = np.full((200, 600, 3), 255, np.uint8)
    cv2.line(img, (50, 100), (550, 100), (0, 0, 0), 8)
    ruta = tmp_path / "gruesa.png"
    cv2.imwrite(str(ruta), img)

    resultado = vectorizar(ruta, OpcionesVectorizado(tolerancia=1.0))
    assert resultado.n_trazos == 1

    puntos = resultado.documento.entidades[0].puntos
    alturas = {round(y) for _, y in puntos}
    assert len(alturas) <= 2, "el trazo se ha desdoblado en los dos bordes"


# -- escala --------------------------------------------------------------


def test_sin_calibrar_avisa(rectangulo: Path) -> None:
    resultado = vectorizar(rectangulo, OpcionesVectorizado())
    assert resultado.documento.unidad is Unidad.SIN_DEFINIR
    assert any("no tiene escala real" in a.mensaje for a in resultado.documento.avisos)


def test_la_calibracion_da_medidas_reales(rectangulo: Path) -> None:
    """Marcando los 400 px del lado largo como 8 m, debe medir 8 m."""
    escala = calcular_escala((100.0, 100.0), (500.0, 100.0), 8.0)
    resultado = vectorizar(
        rectangulo,
        OpcionesVectorizado(escala=escala, unidad=Unidad.METROS, tolerancia=1.0),
    )

    extension = resultado.documento.extension()
    assert extension.ancho == pytest.approx(8.0, rel=0.02)
    assert resultado.documento.unidad is Unidad.METROS


def test_dos_puntos_iguales_no_calibran() -> None:
    with pytest.raises(VectorizacionError):
        calcular_escala((10.0, 10.0), (10.0, 10.0), 5.0)


# -- estrategias de capa -------------------------------------------------


def test_estrategia_unica(rectangulo: Path) -> None:
    resultado = vectorizar(
        rectangulo, OpcionesVectorizado(estrategia=EstrategiaCapas.UNICA)
    )
    con_contenido = [n for n, c in resultado.documento.capas.items() if c.n_entidades]
    assert con_contenido == ["IMAGEN"]


def test_estrategia_por_grosor(dos_grosores: Path) -> None:
    resultado = vectorizar(
        dos_grosores, OpcionesVectorizado(estrategia=EstrategiaCapas.GROSOR)
    )
    con_contenido = {n for n, c in resultado.documento.capas.items() if c.n_entidades}
    assert con_contenido == {"TRAZO_FINO", "TRAZO_GRUESO"}


def test_el_grosor_avisa_de_que_no_interpreta(dos_grosores: Path) -> None:
    resultado = vectorizar(
        dos_grosores, OpcionesVectorizado(estrategia=EstrategiaCapas.GROSOR)
    )
    assert any("no de significado" in a.detalle for a in resultado.documento.avisos)


def test_estrategia_por_color(tmp_path: Path) -> None:
    img = np.full((300, 600, 3), 255, np.uint8)
    cv2.line(img, (50, 100), (550, 100), (0, 0, 220), 4)   # rojo
    cv2.line(img, (50, 200), (550, 200), (220, 0, 0), 4)   # azul
    ruta = tmp_path / "colores.png"
    cv2.imwrite(str(ruta), img)

    resultado = vectorizar(
        ruta, OpcionesVectorizado(estrategia=EstrategiaCapas.COLOR, n_colores=3)
    )
    con_contenido = [n for n, c in resultado.documento.capas.items() if c.n_entidades]
    assert len(con_contenido) >= 2, "no ha separado los dos colores"


# -- integración con el resto --------------------------------------------


def test_lo_vectorizado_se_exporta_a_dxf(rectangulo: Path, tmp_path: Path) -> None:
    """El documento vectorizado no tiene origen ezdxf y debe exportarse igual."""
    resultado = vectorizar(rectangulo, OpcionesVectorizado(tolerancia=1.0))
    destino = tmp_path / "vectorizado.dxf"
    escribir_dxf(resultado.documento, ["IMAGEN"], destino)

    devuelto = leer_dxf(destino)
    assert devuelto.capas["IMAGEN"].n_entidades == resultado.n_trazos


def test_lo_vectorizado_se_exporta_a_svg(rectangulo: Path, tmp_path: Path) -> None:
    resultado = vectorizar(rectangulo, OpcionesVectorizado(tolerancia=1.0))
    destino = tmp_path / "vectorizado.svg"
    escribir_svg(resultado.documento, ["IMAGEN"], destino)
    assert destino.is_file()
    assert "inkscape:groupmode" in destino.read_text(encoding="utf-8")


def test_advierte_de_que_el_resultado_es_interpretado(rectangulo: Path) -> None:
    """El usuario debe saber que esto no es una lectura, sino una deducción."""
    resultado = vectorizar(rectangulo, OpcionesVectorizado())
    assert any("revisarlo" in a.detalle for a in resultado.documento.avisos)


def test_una_imagen_en_blanco_lo_dice(tmp_path: Path) -> None:
    ruta = tmp_path / "blanco.png"
    cv2.imwrite(str(ruta), np.full((200, 200, 3), 255, np.uint8))

    resultado = vectorizar(ruta, OpcionesVectorizado())
    assert resultado.n_trazos == 0
    assert any(a.nivel == "error" for a in resultado.documento.avisos)
