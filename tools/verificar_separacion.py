"""Comprueba una separación releyendo lo generado.

Vuelve a leer cada DXF producido y contrasta el recuento de entidades y la
envolvente contra el plano de partida. Es la comprobación que detecta una
exportación que «funciona» pero entrega geometría desplazada o incompleta.

    .venv\\Scripts\\python.exe tools/verificar_separacion.py plano.dxf carpeta_salida
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

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from arqueocad.io import leer, leer_dxf  # noqa: E402

#: Tolerancia de la comparación de coordenadas, en unidades de dibujo. Con
#: planos en metros equivale a una centésima de milímetro.
TOLERANCIA = 1e-5


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    original = leer(Path(sys.argv[1]))
    carpeta = Path(sys.argv[2])

    print(f"Original: {len(original.entidades)} entidades\n")
    print(f"{'capa':<32}{'orig':>6}{'copia':>7}   desplazamiento")
    print("-" * 70)

    fallos = 0
    total_copiadas = 0

    for archivo in sorted(carpeta.glob("*.dxf")):
        copia = leer_dxf(archivo)
        # El nombre de la capa se deduce del archivo, pero se comprueba contra
        # las capas con contenido para no depender del nombrado.
        con_contenido = [n for n, c in copia.capas.items() if c.n_entidades > 0]

        for nombre in con_contenido:
            if nombre not in original.capas:
                continue

            n_original = original.capas[nombre].n_entidades
            n_copia = copia.capas[nombre].n_entidades
            total_copiadas += n_copia

            ext_o = original.extension_de_capa(nombre)
            ext_c = copia.extension_de_capa(nombre)
            desplazamiento = max(
                abs(ext_o.x_min - ext_c.x_min),
                abs(ext_o.y_min - ext_c.y_min),
                abs(ext_o.x_max - ext_c.x_max),
                abs(ext_o.y_max - ext_c.y_max),
            ) if not (ext_o.vacia or ext_c.vacia) else 0.0

            ok = n_original == n_copia and desplazamiento < TOLERANCIA
            marca = "  " if ok else "✗ "
            if not ok:
                fallos += 1

            print(
                f"{marca}{nombre:<30}{n_original:>6}{n_copia:>7}   {desplazamiento:.2e}"
            )

    print("-" * 70)
    if fallos:
        print(f"{fallos} discrepancias")
        return 1

    print(f"Sin discrepancias. {total_copiadas} entidades verificadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
