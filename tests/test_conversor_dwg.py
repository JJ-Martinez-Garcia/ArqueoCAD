"""Pruebas de la entrada DWG.

La conversión depende de un programa externo que puede no estar instalado. Las
pruebas que lo necesitan se saltan solas; las demás comprueban lo que sí puede
verificarse siempre: la identificación de la versión del archivo, la elección
del conversor y la claridad del mensaje cuando no hay ninguno.
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

import os
from pathlib import Path

import pytest

from arqueocad.io import (
    ConversionDWGError,
    SinConversor,
    convertir,
    detectar,
    leer,
    version_dwg,
)
from arqueocad.io.conversor_dwg import FIABLES_EN_LIBREDWG, VERSIONES

#: Plano DWG real con el que contrastar la conversión. No se incluye en el
#: repositorio: la planimetría de excavación no es material publicable, y cada
#: cual usará la suya. Se indica con una variable de entorno:
#:
#:     set ARQUEOCAD_DWG_PRUEBA=C:\ruta\a\plano.dwg
#:
#: Si además existe un DXF con el mismo nombre, se comprueba que ambos den el
#: mismo resultado, que es la verificación que decide si la conversión es fiable.
_RUTA = os.environ.get("ARQUEOCAD_DWG_PRUEBA", "")
DWG_REAL = Path(_RUTA) if _RUTA else None

hay_conversor = pytest.mark.skipif(
    not detectar(), reason="no hay ningún conversor de DWG instalado"
)
hay_plano = pytest.mark.skipif(
    DWG_REAL is None or not DWG_REAL.is_file(),
    reason="no se ha indicado un plano DWG de prueba (ARQUEOCAD_DWG_PRUEBA)",
)


# -- identificación de la versión ---------------------------------------


def test_identifica_la_version(tmp_path: Path) -> None:
    plano = tmp_path / "plano.dwg"
    plano.write_bytes(b"AC1024" + b"\x00" * 32)

    firma, version = version_dwg(plano)
    assert firma == "AC1024"
    assert version == "AutoCAD 2010"


def test_una_version_desconocida_no_revienta(tmp_path: Path) -> None:
    plano = tmp_path / "raro.dwg"
    plano.write_bytes(b"AC9999" + b"\x00" * 32)

    _, version = version_dwg(plano)
    assert version == "desconocida"


def test_las_versiones_fiables_son_las_antiguas() -> None:
    """LibreDWG cubre con garantías hasta R2000, y parcialmente lo posterior.

    Es lo que justifica avisar antes de abrir un DWG moderno con ese conversor.
    """
    assert "AC1015" in FIABLES_EN_LIBREDWG          # AutoCAD 2000
    assert "AC1024" not in FIABLES_EN_LIBREDWG      # AutoCAD 2010
    assert "AC1032" not in FIABLES_EN_LIBREDWG      # AutoCAD 2018
    assert set(FIABLES_EN_LIBREDWG) <= set(VERSIONES)


@hay_plano
def test_identifica_la_version_del_plano_real() -> None:
    """La versión debe reconocerse, sea cual sea el plano que se indique."""
    firma, version = version_dwg(DWG_REAL)
    assert firma.startswith("AC")
    assert version != "desconocida", f"firma no catalogada: {firma}"


# -- ausencia de conversor ----------------------------------------------


def test_sin_conversor_el_mensaje_explica_que_hacer(tmp_path: Path, monkeypatch) -> None:
    """El error debe decir por qué ocurre y cómo resolverlo, no solo fallar."""
    monkeypatch.setattr("arqueocad.io.conversor_dwg.detectar", lambda: [])

    plano = tmp_path / "plano.dwg"
    plano.write_bytes(b"AC1024" + b"\x00" * 32)

    with pytest.raises(SinConversor) as error:
        convertir(plano)

    mensaje = str(error.value)
    assert "propietario" in mensaje
    assert "opendesign.com" in mensaje
    assert "AutoCAD" in mensaje


def test_archivo_inexistente() -> None:
    with pytest.raises(FileNotFoundError):
        convertir(Path("no_existe.dwg"))


# -- conversión real -----------------------------------------------------


@hay_conversor
@hay_plano
def test_convierte_el_plano_real(tmp_path: Path) -> None:
    destino, avisos = convertir(DWG_REAL, tmp_path)

    assert destino.is_file()
    assert destino.stat().st_size > 0
    _, version = version_dwg(DWG_REAL)
    assert any(version in a.mensaje for a in avisos)


@hay_conversor
@hay_plano
def test_el_dwg_se_abre_como_un_plano_normal() -> None:
    """Tras la conversión debe comportarse como cualquier otro documento."""
    documento = leer(DWG_REAL)

    assert documento.formato.value == "dwg"
    # La ruta que se muestra es la del archivo que abrió el usuario, no la del
    # intermedio, pero este queda registrado para poder informar.
    assert documento.ruta == str(DWG_REAL)
    assert documento.ruta_intermedia is not None
    assert documento.entidades


@hay_conversor
@hay_plano
def test_el_dwg_coincide_con_su_dxf_equivalente() -> None:
    """El mismo plano existe en los dos formatos: deben dar lo mismo.

    Es la comprobación que decide si la conversión es fiable, porque contrasta
    contra un resultado conocido en lugar de darla por buena.
    """
    dxf = DWG_REAL.with_suffix(".dxf")
    if not dxf.is_file():
        pytest.skip("no está el DXF equivalente")

    desde_dwg = leer(DWG_REAL)
    desde_dxf = leer(dxf)

    capas_dwg = {n for n, c in desde_dwg.capas.items() if c.n_entidades > 0}
    capas_dxf = {n for n, c in desde_dxf.capas.items() if c.n_entidades > 0}
    assert capas_dwg == capas_dxf

    ext_dwg = desde_dwg.extension()
    ext_dxf = desde_dxf.extension()
    assert ext_dwg.ancho == pytest.approx(ext_dxf.ancho, rel=1e-3)
    assert ext_dwg.alto == pytest.approx(ext_dxf.alto, rel=1e-3)
