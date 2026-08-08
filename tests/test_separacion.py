"""Pruebas de la separación por capas y de los escritores.

Las pruebas de ida y vuelta son el núcleo: comprueban que un plano separado y
vuelto a leer conserva la geometría, la escala y el reparto entre capas. Sin
ellas, un error de exportación solo se detectaría al abrir el archivo en
AutoCAD, cuando el plano ya está en la publicación.
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

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from arqueocad.core import Documento, Formato, Modo, Opciones, Unidad, separar
from arqueocad.core.nombres import sanear, unicos
from arqueocad.io import EscrituraDXFError, escribir_dxf, escribir_svg, leer_dxf

import plano_de_prueba

ESPACIO_SVG = "http://www.w3.org/2000/svg"
ESPACIO_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"


@pytest.fixture(scope="module")
def documento(tmp_path_factory) -> Documento:
    ruta = plano_de_prueba.construir(
        tmp_path_factory.mktemp("origen") / "excavacion.dxf"
    )
    return leer_dxf(ruta)


# -- nombres de archivo --------------------------------------------------


def test_conserva_acentos_y_espacios() -> None:
    """Los tres sistemas admiten acentos; quitarlos fundiría capas distintas."""
    assert sanear("SARCÓFAGO_2024") == "SARCÓFAGO_2024"
    assert sanear("TEXTO 2024") == "TEXTO 2024"


def test_sustituye_los_caracteres_prohibidos() -> None:
    assert sanear("MUROS/FASE 2") == "MUROS_FASE 2"
    assert sanear('COTAS: "nivel"') == "COTAS_ _nivel_"


def test_no_confunde_capas_que_solo_difieren_en_la_tilde() -> None:
    """`PERIMETRO_TUMBA` y `PERÍMETRO_EXCAVADO` deben ir a archivos distintos."""
    asignados = unicos(["PERIMETRO_TUMBA_2024", "PERÍMETRO_EXCAVADO_2024"])
    assert len(set(asignados.values())) == 2


def test_resuelve_las_colisiones_con_sufijo() -> None:
    asignados = unicos(["A/B", "A:B"])
    assert asignados["A/B"] == "A_B"
    assert asignados["A:B"] == "A_B_2"


def test_evita_los_nombres_reservados_de_windows() -> None:
    assert sanear("CON").startswith("_")
    assert sanear("aux").startswith("_")


def test_ignora_diferencias_de_mayusculas() -> None:
    """Windows y macOS no las distinguen: dos capas se pisarían el archivo."""
    asignados = unicos(["MUROS", "Muros"])
    assert asignados["MUROS"].casefold() != asignados["Muros"].casefold()


# -- exportación a DXF ---------------------------------------------------


def test_el_dxf_separado_conserva_la_geometria(documento: Documento, tmp_path: Path) -> None:
    """Ida y vuelta: lo exportado debe volver a leerse igual."""
    destino = tmp_path / "solo_muros.dxf"
    escribir_dxf(documento, ["MUROS"], destino)

    devuelto = leer_dxf(destino)
    assert devuelto.capas["MUROS"].n_entidades == documento.capas["MUROS"].n_entidades

    original = documento.extension_de_capa("MUROS")
    copia = devuelto.extension_de_capa("MUROS")
    assert copia.x_min == pytest.approx(original.x_min, abs=1e-6)
    assert copia.y_max == pytest.approx(original.y_max, abs=1e-6)


def test_el_dxf_separado_conserva_las_unidades(documento: Documento, tmp_path: Path) -> None:
    """Perder la escala es el error más grave y el más difícil de ver."""
    destino = tmp_path / "con_unidades.dxf"
    escribir_dxf(documento, ["MUROS"], destino)
    assert leer_dxf(destino).unidad is Unidad.METROS


def test_el_dxf_separado_solo_lleva_lo_pedido(documento: Documento, tmp_path: Path) -> None:
    destino = tmp_path / "solo_ue2.dxf"
    escribir_dxf(documento, ["UE-2"], destino)

    devuelto = leer_dxf(destino)
    capas_con_contenido = {
        nombre for nombre, capa in devuelto.capas.items() if capa.n_entidades > 0
    }
    assert capas_con_contenido == {"UE-2"}


def test_conserva_el_spline_sin_aplanar(documento: Documento, tmp_path: Path) -> None:
    """La exportación copia la entidad original, no la poligonal del visor."""
    destino = tmp_path / "curvas.dxf"
    escribir_dxf(documento, ["UE-101"], destino)

    import ezdxf

    tipos = {e.dxftype() for e in ezdxf.readfile(destino).modelspace()}
    assert "SPLINE" in tipos, "el spline ha llegado aplanado"
    assert "ELLIPSE" in tipos


def test_conserva_el_sombreado(documento: Documento, tmp_path: Path) -> None:
    destino = tmp_path / "sombreado.dxf"
    escribir_dxf(documento, ["UE-10"], destino)

    import ezdxf

    tipos = {e.dxftype() for e in ezdxf.readfile(destino).modelspace()}
    assert "HATCH" in tipos


def test_explotar_reparte_el_bloque_entre_capas(documento: Documento, tmp_path: Path) -> None:
    """Sin explotar, el bloque viaja entero con la capa de inserción.

    El bloque NORTE se inserta en TEXTOS y en MUROS, pero su círculo pertenece a
    UE-101. Al desplegarlo, ese círculo debe quedar fuera de un archivo que solo
    pida TEXTOS.
    """
    import ezdxf

    entero = tmp_path / "entero.dxf"
    escribir_dxf(documento, ["TEXTOS"], entero, explotar_bloques=False)
    assert "INSERT" in {e.dxftype() for e in ezdxf.readfile(entero).modelspace()}

    desplegado = tmp_path / "desplegado.dxf"
    escribir_dxf(documento, ["TEXTOS"], desplegado, explotar_bloques=True)
    contenido = ezdxf.readfile(desplegado).modelspace()
    assert "INSERT" not in {e.dxftype() for e in contenido}
    assert all(e.dxf.layer == "TEXTOS" for e in contenido)


def test_sin_capas_falla_con_mensaje_claro(documento: Documento, tmp_path: Path) -> None:
    with pytest.raises(EscrituraDXFError):
        escribir_dxf(documento, [], tmp_path / "vacio.dxf")


# -- exportación a SVG ---------------------------------------------------


def test_el_svg_usa_capas_de_inkscape(documento: Documento, tmp_path: Path) -> None:
    """Un grupo sin `inkscape:groupmode` no es una capa, es un grupo."""
    destino = tmp_path / "capas.svg"
    escribir_svg(documento, ["MUROS", "UE-2"], destino)

    raiz = ET.parse(destino).getroot()
    capas = [
        g for g in raiz.iter(f"{{{ESPACIO_SVG}}}g")
        if g.get(f"{{{ESPACIO_INKSCAPE}}}groupmode") == "layer"
    ]
    etiquetas = [g.get(f"{{{ESPACIO_INKSCAPE}}}label") for g in capas]
    assert etiquetas == ["MUROS", "UE-2"]


def test_el_svg_declara_medidas_reales(documento: Documento, tmp_path: Path) -> None:
    """El plano está en metros: cada unidad de dibujo son 1.000 mm de papel."""
    destino = tmp_path / "medidas.svg"
    escribir_svg(documento, ["MUROS"], destino)

    raiz = ET.parse(destino).getroot()
    assert raiz.get("width", "").endswith("mm")
    ancho_mm = float(raiz.get("width").removesuffix("mm"))
    ancho_real = documento.extension_de_capa("MUROS").ancho
    assert ancho_mm == pytest.approx(ancho_real * 1000, rel=1e-4)


def test_la_escala_reduce_el_tamanio_fisico(documento: Documento, tmp_path: Path) -> None:
    """A 1:50 el dibujo debe ocupar en papel la cincuentava parte."""
    tamanio_real = tmp_path / "real.svg"
    escala_50 = tmp_path / "escala50.svg"
    escribir_svg(documento, ["MUROS"], tamanio_real)
    escribir_svg(documento, ["MUROS"], escala_50, escala=50)

    def ancho(ruta: Path) -> float:
        return float(ET.parse(ruta).getroot().get("width").removesuffix("mm"))

    assert ancho(tamanio_real) / ancho(escala_50) == pytest.approx(50, rel=1e-4)


def test_el_viewbox_conserva_las_proporciones(documento: Documento, tmp_path: Path) -> None:
    destino = tmp_path / "proporciones.svg"
    escribir_svg(documento, ["MUROS"], destino)

    raiz = ET.parse(destino).getroot()
    _, _, ancho, alto = (float(v) for v in raiz.get("viewBox").split())
    original = documento.extension_de_capa("MUROS")
    assert ancho / alto == pytest.approx(original.ancho / original.alto, rel=1e-6)


def test_el_blanco_se_convierte_en_negro(documento: Documento, tmp_path: Path) -> None:
    """El color 7 de AutoCAD se ve blanco en pantalla, pero se imprime negro.

    Sin esta conversión, el marco del cajetín y buena parte de la rotulación
    desaparecen al abrir el SVG en Inkscape, que trabaja sobre fondo blanco.
    """
    destino = tmp_path / "papel.svg"
    escribir_svg(documento, ["MUROS"], destino)
    contenido = destino.read_text(encoding="utf-8")

    assert "#ffffff" not in contenido
    assert "#000000" in contenido


def test_puede_conservarse_el_color_de_pantalla(documento: Documento, tmp_path: Path) -> None:
    destino = tmp_path / "pantalla.svg"
    escribir_svg(documento, ["MUROS"], destino, colores_para_papel=False)
    assert "#ffffff" in destino.read_text(encoding="utf-8")


def test_exporta_las_capas_visibles_aunque_estuvieran_apagadas(
    documento: Documento, tmp_path: Path
) -> None:
    """Seleccionar una capa para exportar significa quererla en el resultado.

    Que estuviese congelada o apagada en el archivo de origen es un estado de
    trabajo del dibujante, no una instrucción sobre la exportación.
    """
    documento.capas["MUROS"].congelada = True
    try:
        destino = tmp_path / "congelada.svg"
        escribir_svg(documento, ["MUROS"], destino)
        assert "display:none" not in destino.read_text(encoding="utf-8")
    finally:
        documento.capas["MUROS"].congelada = False


def test_el_svg_avisa_si_faltan_las_unidades(tmp_path: Path) -> None:
    """Sin unidades no puede declararse una medida física, y hay que decirlo."""
    ruta = plano_de_prueba.construir(tmp_path / "sin_unidades.dxf")

    import ezdxf

    doc = ezdxf.readfile(ruta)
    doc.header["$INSUNITS"] = 0
    doc.saveas(ruta)

    documento = leer_dxf(ruta)
    avisos = escribir_svg(documento, ["MUROS"], tmp_path / "sin_medidas.svg")

    assert any("no declara sus unidades" in a.mensaje for a in avisos)
    raiz = ET.parse(tmp_path / "sin_medidas.svg").getroot()
    assert raiz.get("width") is None
    assert raiz.get("viewBox") is not None


# -- separación completa -------------------------------------------------


def test_genera_un_archivo_por_capa(documento: Documento, tmp_path: Path) -> None:
    resultado = separar(
        documento,
        documento.nombres_de_capa(),
        Opciones(carpeta=tmp_path, modo=Modo.POR_CAPA, formatos=(Formato.DXF,)),
    )

    assert resultado.total_archivos > 0
    assert not resultado.hubo_problemas
    for archivo in resultado.archivos:
        assert archivo.ruta.is_file()
        assert archivo.tamanio > 0


def test_descarta_las_capas_auxiliares_y_vacias(documento: Documento, tmp_path: Path) -> None:
    """«Defpoints» y las capas sin contenido no deben generar archivo."""
    resultado = separar(
        documento,
        documento.nombres_de_capa(),
        Opciones(carpeta=tmp_path, modo=Modo.POR_CAPA),
    )

    generados = {a.ruta.stem for a in resultado.archivos}
    assert not any("Defpoints" in nombre for nombre in generados)
    assert "Defpoints" in resultado.omitidas


def test_genera_los_dos_formatos_a_la_vez(documento: Documento, tmp_path: Path) -> None:
    resultado = separar(
        documento,
        ["MUROS", "UE-2"],
        Opciones(carpeta=tmp_path, formatos=(Formato.DXF, Formato.SVG)),
    )

    sufijos = {a.ruta.suffix for a in resultado.archivos}
    assert sufijos == {".dxf", ".svg"}
    assert resultado.total_archivos == 4


def test_modo_unico_reune_todo_en_un_archivo(documento: Documento, tmp_path: Path) -> None:
    resultado = separar(
        documento,
        ["MUROS", "UE-2", "UE-10"],
        Opciones(carpeta=tmp_path, modo=Modo.UNICO),
    )

    assert resultado.total_archivos == 1
    devuelto = leer_dxf(resultado.archivos[0].ruta)
    con_contenido = {n for n, c in devuelto.capas.items() if c.n_entidades > 0}
    # UE-101 entra de rebote: el bloque NORTE se inserta en MUROS y su círculo
    # está dibujado en esa capa. Es el comportamiento del formato, y por eso la
    # exportación lo advierte.
    assert {"MUROS", "UE-2", "UE-10"} <= con_contenido
    assert "TEXTOS" not in con_contenido


def test_avisa_de_las_capas_que_arrastran_los_bloques(
    documento: Documento, tmp_path: Path
) -> None:
    """Quien pide una sola capa debe saber qué más le llega dentro del bloque."""
    avisos = escribir_dxf(documento, ["MUROS"], tmp_path / "con_bloque.dxf")
    arrastre = [a for a in avisos if "dentro de bloques" in a.mensaje]
    assert arrastre, "no se ha advertido del contenido del bloque"
    assert "UE-101" in arrastre[0].detalle


def test_desplegar_evita_el_arrastre_de_capas(
    documento: Documento, tmp_path: Path
) -> None:
    """Con los bloques desplegados, el archivo lleva solo lo pedido."""
    destino = tmp_path / "limpio.dxf"
    escribir_dxf(documento, ["MUROS"], destino, explotar_bloques=True)

    devuelto = leer_dxf(destino)
    con_contenido = {n for n, c in devuelto.capas.items() if c.n_entidades > 0}
    assert con_contenido == {"MUROS"}


def test_modo_por_grupo(documento: Documento, tmp_path: Path) -> None:
    resultado = separar(
        documento,
        documento.nombres_de_capa(),
        Opciones(
            carpeta=tmp_path,
            modo=Modo.POR_GRUPO,
            grupos={
                "estructuras": ["MUROS"],
                "unidades": ["UE-2", "UE-10", "UE-101"],
            },
        ),
    )

    assert resultado.total_archivos == 2
    nombres = sorted(a.ruta.stem for a in resultado.archivos)
    assert nombres == ["excavacion_estructuras", "excavacion_unidades"]


def test_informa_del_avance(documento: Documento, tmp_path: Path) -> None:
    """La interfaz necesita el avance para no parecer colgada con planos grandes."""
    llamadas: list[tuple[int, int]] = []
    separar(
        documento,
        ["MUROS", "UE-2"],
        Opciones(carpeta=tmp_path),
        progreso=lambda hechos, total, _: llamadas.append((hechos, total)),
    )

    assert llamadas, "no se ha informado del avance"
    assert llamadas[-1][0] == llamadas[-1][1], "el avance no llega al final"
