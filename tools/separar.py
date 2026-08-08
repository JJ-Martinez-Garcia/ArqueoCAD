"""Separa un plano por capas desde la línea de órdenes.

    .venv\\Scripts\\python.exe tools/separar.py plano.dxf carpeta_salida [opciones]

Opciones:
    --svg        genera también SVG además de DXF
    --solo-svg   genera únicamente SVG
    --explotar   despliega los bloques para repartir su geometría por capas
    --unico      reúne todas las capas en un solo archivo en vez de uno por capa

Sirve para comprobar el resultado sobre planos reales sin pasar por la interfaz,
y como base del proceso por lotes.
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

from arqueocad.core import Formato, Modo, Opciones, separar  # noqa: E402
from arqueocad.io import leer  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    plano = Path(sys.argv[1])
    carpeta = Path(sys.argv[2])
    opciones_texto = sys.argv[3:]

    formatos = [Formato.DXF]
    if "--svg" in opciones_texto:
        formatos.append(Formato.SVG)
    if "--solo-svg" in opciones_texto:
        formatos = [Formato.SVG]

    documento = leer(plano)
    print(f"{plano.name}: {len(documento.entidades)} entidades, {len(documento.capas)} capas\n")

    resultado = separar(
        documento,
        documento.nombres_de_capa(),
        Opciones(
            carpeta=carpeta,
            modo=Modo.UNICO if "--unico" in opciones_texto else Modo.POR_CAPA,
            formatos=tuple(formatos),
            explotar_bloques="--explotar" in opciones_texto,
            prefijo=(
                f"{plano.stem}_TODAS_LAS_CAPAS" if "--unico" in opciones_texto else ""
            ),
        ),
    )

    for archivo in resultado.archivos:
        print(
            f"  {archivo.ruta.name:<48} {archivo.n_entidades:>5} ent. "
            f"{archivo.tamanio / 1024:>8.1f} KB"
        )

    print(f"\n{resultado.total_archivos} archivos en {carpeta}")

    if resultado.omitidas:
        print(f"Capas omitidas: {', '.join(resultado.omitidas)}")

    if resultado.avisos:
        print(f"\n-- Avisos ({len(resultado.avisos)}) --")
        for aviso in resultado.avisos:
            print(f"  [{aviso.nivel}] {aviso.mensaje}")
            if aviso.detalle:
                print(f"      {aviso.detalle}")

    return 1 if resultado.hubo_problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
