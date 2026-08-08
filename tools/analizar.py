"""Informe de lectura de un plano, sin abrir la interfaz.

Sirve para comprobar deprisa qué encuentra ArqueoCAD en un archivo real: capas,
tipos de entidad, extensión, unidades y todas las incidencias registradas.

    .venv\\Scripts\\python.exe tools/analizar.py plano.dxf
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
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from arqueocad.core.unidades import nombre as nombre_unidad  # noqa: E402
from arqueocad.io import leer  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    ruta = Path(sys.argv[1])
    inicio = time.perf_counter()
    documento = leer(ruta)
    transcurrido = time.perf_counter() - inicio

    print(f"=== {ruta.name} ===")
    print(f"Leído en {transcurrido:.2f} s")
    print(f"Unidad declarada : {nombre_unidad(documento.unidad)}")
    print(f"Entidades        : {len(documento.entidades):,}".replace(",", "."))
    print(f"Capas            : {len(documento.capas)}")

    ext = documento.extension()
    if not ext.vacia:
        print(
            f"Extensión        : X {ext.x_min:,.2f} … {ext.x_max:,.2f}   "
            f"Y {ext.y_min:,.2f} … {ext.y_max:,.2f}"
        )
        print(f"Tamaño           : {ext.ancho:,.2f} × {ext.alto:,.2f} unidades")

    tipos = Counter(e.tipo_origen for e in documento.entidades)
    print("\n-- Tipos de entidad --")
    for tipo, n in tipos.most_common():
        print(f"  {tipo:<14} {n:>8,}".replace(",", "."))

    print("\n-- Capas --")
    for nombre in documento.nombres_de_capa():
        capa = documento.capas[nombre]
        marca = "aux" if capa.auxiliar else "   "
        contenido = ", ".join(sorted(capa.tipos_presentes)) or "(vacía)"
        print(f"  {marca} {nombre:<28} {capa.n_entidades:>7,}  {contenido}".replace(",", "."))

    if documento.avisos:
        print(f"\n-- Avisos ({len(documento.avisos)}) --")
        vistos: Counter[str] = Counter()
        for aviso in documento.avisos:
            vistos[f"[{aviso.nivel}] {aviso.mensaje}"] += 1
        for mensaje, n in vistos.most_common(30):
            sufijo = f"  (× {n})" if n > 1 else ""
            print(f"  {mensaje}{sufijo}")
    else:
        print("\nSin avisos.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
