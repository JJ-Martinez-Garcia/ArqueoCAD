"""Genera un DXF sintético que imita un plano de excavación.

Reúne a propósito los tipos de entidad que más problemas dan en una conversión:
polilíneas con tramos curvos, splines, sombreados, textos, sólidos y bloques
con geometría repartida entre la capa «0» y una capa propia.
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

import math
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

#: Capas con nomenclatura de excavación, incluida la numeración que delata un
#: orden alfabético mal hecho (UE-2 debe ir antes que UE-10).
CAPAS = {
    "UE-2": 1,
    "UE-10": 3,
    "UE-101": 5,
    "MUROS": 7,
    "COTAS": 4,
    "TEXTOS": 2,
}


def construir(destino: str | Path) -> Path:
    """Escribe el plano de prueba y devuelve su ruta."""
    destino = Path(destino)
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 6  # metros

    for nombre, color in CAPAS.items():
        doc.layers.add(name=nombre, color=color)

    _definir_bloque(doc)
    msp = doc.modelspace()

    # Muro: polilínea cerrada con dos tramos rectos y uno curvo (bulge).
    msp.add_lwpolyline(
        [(0, 0, 0, 0, 0), (10, 0, 0, 0, 0.5), (10, 4, 0, 0, 0), (0, 4, 0, 0, 0)],
        format="xyseb",
        close=True,
        dxfattribs={"layer": "MUROS"},
    )

    # Unidades estratigráficas: contornos de distinta naturaleza.
    msp.add_circle((3, 2), radius=1.2, dxfattribs={"layer": "UE-2"})
    msp.add_arc((7, 2), radius=1.0, start_angle=0, end_angle=180,
                dxfattribs={"layer": "UE-10"})
    msp.add_ellipse((5, 6), major_axis=(2, 0), ratio=0.5,
                    dxfattribs={"layer": "UE-101"})
    msp.add_spline(
        [(0, 8), (2, 9.5), (5, 7.5), (8, 9), (10, 8)],
        dxfattribs={"layer": "UE-101"},
    )
    msp.add_line((0, 0), (10, 4), dxfattribs={"layer": "UE-2"})

    # Sombreado sólido, del tipo que se usa para marcar una unidad excavada.
    sombreado = msp.add_hatch(color=2, dxfattribs={"layer": "UE-10"})
    sombreado.paths.add_polyline_path(
        [(1, 5), (3, 5), (3, 7), (1, 7)], is_closed=True
    )

    # Sólido de cuatro vértices: comprueba el reordenado de la diagonal.
    msp.add_solid(
        [(6, 0.5), (7, 0.5), (6, 1.5), (7, 1.5)],
        dxfattribs={"layer": "MUROS"},
    )

    # Rotulación.
    msp.add_text(
        "UE 101", height=0.4, dxfattribs={"layer": "TEXTOS"}
    ).set_placement((5, 6), align=TextEntityAlignment.MIDDLE_CENTER)
    msp.add_mtext(
        "Sector A\\PCampaña 2026", dxfattribs={"layer": "TEXTOS", "char_height": 0.3}
    ).set_location((0.5, 10.5))

    # Cotas de nivel como puntos con su etiqueta.
    for x, y, z in [(2, 1, 12.34), (8, 3, 12.11), (5, 7, 12.52)]:
        msp.add_point((x, y), dxfattribs={"layer": "COTAS"})
        msp.add_text(
            f"{z:.2f}", height=0.25, dxfattribs={"layer": "COTAS"}
        ).set_placement((x + 0.2, y + 0.2))

    # Cota lineal: en realidad es un bloque anónimo que hay que desplegar.
    msp.add_linear_dim(
        base=(0, -1.5), p1=(0, 0), p2=(10, 0), dxfattribs={"layer": "COTAS"}
    ).render()

    # Dos inserciones del mismo bloque, una de ellas girada y a escala.
    msp.add_blockref("NORTE", (11.5, 9), dxfattribs={"layer": "TEXTOS"})
    msp.add_blockref(
        "NORTE", (11.5, 1),
        dxfattribs={"layer": "MUROS", "rotation": 45, "xscale": 0.5, "yscale": 0.5},
    )

    doc.saveas(destino)
    return destino


def _definir_bloque(doc) -> None:
    """Bloque con geometría repartida entre la capa «0» y una capa propia.

    Es el caso que decide si la separación por capas funciona: la parte en «0»
    debe heredar la capa de inserción y la parte en «UE-101» debe conservarse.
    """
    bloque = doc.blocks.new(name="NORTE")
    bloque.add_line((0, 0), (0, 1), dxfattribs={"layer": "0"})
    bloque.add_line((0, 1), (-0.3, 0.6), dxfattribs={"layer": "0"})
    bloque.add_line((0, 1), (0.3, 0.6), dxfattribs={"layer": "0"})
    bloque.add_circle((0, 0), radius=0.15, dxfattribs={"layer": "UE-101"})


if __name__ == "__main__":
    ruta = construir(Path(__file__).with_name("plano_prueba.dxf"))
    print(f"Escrito: {ruta}")
