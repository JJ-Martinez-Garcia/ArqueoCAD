"""Compara dos planos que deberían ser el mismo.

Pensado para contrastar un DWG contra su DXF equivalente y decidir si la
conversión es fiable, en lugar de darla por buena porque «abre».

    .venv\\Scripts\\python.exe tools/comparar.py plano.dwg plano.dxf
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
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from arqueocad.io import leer  # noqa: E402

#: Diferencia máxima admitida en coordenadas, en unidades de dibujo.
TOLERANCIA = 1e-6


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    uno = leer(Path(sys.argv[1]))
    otro = leer(Path(sys.argv[2]))

    print(f"A: {Path(uno.ruta).name}   {len(uno.entidades)} entidades")
    print(f"B: {Path(otro.ruta).name}   {len(otro.entidades)} entidades\n")

    problemas = 0

    if uno.unidad != otro.unidad:
        print(f"✗ Unidades distintas: {uno.unidad.name} frente a {otro.unidad.name}")
        problemas += 1
    else:
        print(f"  Unidad: {uno.unidad.name}")

    tipos_a = Counter(e.tipo_origen for e in uno.entidades)
    tipos_b = Counter(e.tipo_origen for e in otro.entidades)
    if tipos_a != tipos_b:
        print("✗ Difieren los tipos de entidad:")
        for tipo in sorted(set(tipos_a) | set(tipos_b)):
            if tipos_a[tipo] != tipos_b[tipo]:
                print(f"    {tipo:<14} {tipos_a[tipo]:>6} / {tipos_b[tipo]:>6}")
        problemas += 1
    else:
        print(f"  Tipos de entidad: {len(tipos_a)} distintos, recuentos iguales")

    capas_a = {n for n, c in uno.capas.items() if c.n_entidades > 0}
    capas_b = {n for n, c in otro.capas.items() if c.n_entidades > 0}
    if capas_a != capas_b:
        print("✗ Difieren las capas con contenido:")
        for nombre in sorted(capas_a ^ capas_b):
            print(f"    solo en {'A' if nombre in capas_a else 'B'}: {nombre}")
        problemas += 1
    else:
        print(f"  Capas con contenido: {len(capas_a)}, idénticas")

    print("\n  capa                          A      B   desplazamiento")
    print("  " + "-" * 58)
    for nombre in sorted(capas_a):
        n_a = uno.capas[nombre].n_entidades
        n_b = otro.capas[nombre].n_entidades
        ext_a = uno.extension_de_capa(nombre)
        ext_b = otro.extension_de_capa(nombre)
        desplazamiento = max(
            abs(ext_a.x_min - ext_b.x_min),
            abs(ext_a.y_min - ext_b.y_min),
            abs(ext_a.x_max - ext_b.x_max),
            abs(ext_a.y_max - ext_b.y_max),
        )
        ok = n_a == n_b and desplazamiento < TOLERANCIA
        if not ok:
            problemas += 1
        print(
            f"  {'  ' if ok else '✗ '}{nombre:<26}{n_a:>5}{n_b:>7}   {desplazamiento:.3e}"
        )

    print("  " + "-" * 58)
    if problemas:
        print(f"\n{problemas} discrepancias.")
        return 1

    print("\nLos dos planos son equivalentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
