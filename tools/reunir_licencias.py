"""Reúne los textos de licencia que deben acompañar a ArqueoCAD.

Las licencias MIT y BSD exigen literalmente incluir su aviso de copyright y su
texto completo en toda copia que se distribuya; un listado de nombres no basta.
La LGPL de Qt pide además el texto de la GPL, en la que se apoya.

Los textos se copian de los propios paquetes instalados y de las copias verbatim
que distribuye el proyecto GNU, en lugar de transcribirlos: un texto legal
alterado es peor que ninguno.

    .venv\\Scripts\\python.exe tools/reunir_licencias.py
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

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "licencias"
SITE = RAIZ / ".venv" / "Lib" / "site-packages"

#: Copias verbatim que distribuye el proyecto GNU dentro de Git para Windows.
#: La propia licencia autoriza a copiarlas literalmente.
GNU = Path(r"C:\Program Files\Git\mingw64\share\licenses")
FUENTES_GNU = {
    "GPL-3.0.txt": GNU / "gcc-libs" / "COPYING3",
    "LGPL-3.0.txt": GNU / "libunistring" / "LICENSE.LIB",
}

#: Paquete → (archivo dentro de su .dist-info, nombre de salida).
FUENTES_PAQUETES = {
    "ezdxf": ("LICENSE", "ezdxf-MIT.txt"),
    "svgelements": ("LICENSE", "svgelements-MIT.txt"),
    "pyparsing": ("LICENSE", "pyparsing-MIT.txt"),
    "fonttools": ("LICENSE", "fonttools-MIT.txt"),
    "numpy": ("LICENSE.txt", "numpy-BSD-3.txt"),
}

INDICE = """LICENCIAS DE ARQUEOCAD Y DE SUS COMPONENTES
================================================================================

ArqueoCAD se distribuye bajo la Licencia Pública General de GNU, versión 3
(GPL-3.0). Su texto completo está en:

    GPL-3.0.txt

Eso significa que el programa es libre: puede usarse, copiarse, estudiarse y
modificarse sin pedir permiso. Quien distribuya una versión modificada debe
publicar también su código fuente bajo esta misma licencia.

Código fuente de ArqueoCAD:
    {repositorio}


COMPONENTES DE TERCEROS
--------------------------------------------------------------------------------

ArqueoCAD incorpora las siguientes bibliotecas, cada una con su licencia:

    ezdxf .............. MIT       lectura y escritura de DXF
    svgelements ........ MIT       análisis de SVG
    pyparsing .......... MIT       requerido por ezdxf
    fonttools .......... MIT       requerido por la composición de textos
    NumPy .............. BSD-3     cálculo numérico
    PySide6 / Qt 6 ..... LGPL-3.0  interfaz gráfica

Sus textos están en la subcarpeta «terceros».


AVISO SOBRE QT
--------------------------------------------------------------------------------

Esta aplicación usa la biblioteca Qt 6 a través de PySide6, bajo la Licencia
Pública General Reducida de GNU, versión 3 (LGPL-3.0), cuyo texto está en
terceros/LGPL-3.0.txt. La LGPL se apoya en la GPL-3.0, incluida en GPL-3.0.txt.

Conforme a los términos de la LGPL, quien reciba este programa tiene derecho a
sustituir las bibliotecas de Qt por otra versión. Las bibliotecas se distribuyen
como archivos independientes dentro de la carpeta de la aplicación, de modo que
pueden reemplazarse directamente.

El código fuente de Qt y de PySide6 está disponible en:
    https://download.qt.io/official_releases/QtForPython/
    https://code.qt.io/


ARCHIVOS DWG
--------------------------------------------------------------------------------

ArqueoCAD NO incorpora ningún componente de lectura de DWG, porque es un formato
propietario y cerrado. Los archivos DWG se convierten invocando un programa
externo que instala el propio usuario, habitualmente ODA File Converter, que se
distribuye por separado bajo sus propias condiciones y no forma parte de esta
aplicación.


MARCAS REGISTRADAS
--------------------------------------------------------------------------------

AutoCAD, DWG y DXF son marcas registradas de Autodesk, Inc. Inkscape es marca
registrada de Software Freedom Conservancy. Se mencionan únicamente para
describir la compatibilidad de formatos. ArqueoCAD no está afiliado a Autodesk
ni cuenta con su respaldo o patrocinio.
"""

REPOSITORIO = "https://github.com/JJ-Martinez-Garcia/ArqueoCAD"


def main() -> int:
    terceros = DESTINO / "terceros"
    terceros.mkdir(parents=True, exist_ok=True)

    faltan: list[str] = []

    for nombre, origen in FUENTES_GNU.items():
        if not origen.is_file():
            faltan.append(f"{nombre} (esperado en {origen})")
            continue
        # La GPL va en la raíz por ser la licencia de ArqueoCAD; la LGPL, entre
        # las de terceros, porque es la de Qt.
        salida = DESTINO / nombre if nombre == "GPL-3.0.txt" else terceros / nombre
        shutil.copyfile(origen, salida)
        print(f"  {salida.relative_to(RAIZ)}")

    for paquete, (archivo, salida) in FUENTES_PAQUETES.items():
        origen = _buscar(paquete, archivo)
        if origen is None:
            faltan.append(f"{salida} (no se encuentra la licencia de {paquete})")
            continue
        shutil.copyfile(origen, terceros / salida)
        print(f"  {(terceros / salida).relative_to(RAIZ)}")

    indice = DESTINO / "LEEME.txt"
    indice.write_text(INDICE.format(repositorio=REPOSITORIO), encoding="utf-8")
    print(f"  {indice.relative_to(RAIZ)}")

    if faltan:
        print("\nFALTAN:", file=sys.stderr)
        for falta in faltan:
            print(f"  - {falta}", file=sys.stderr)
        return 1

    print(f"\n{len(list(DESTINO.rglob('*.txt')))} archivos en {DESTINO}")
    return 0


def _buscar(paquete: str, archivo: str) -> Path | None:
    """Localiza un archivo de licencia dentro del .dist-info de un paquete."""
    for carpeta in SITE.glob(f"{paquete}-*.dist-info"):
        for candidato in (carpeta / archivo, carpeta / "licenses" / archivo):
            if candidato.is_file():
                return candidato
        # Algunos paquetes lo guardan bajo una subcarpeta con su propio nombre.
        encontrados = sorted(carpeta.rglob(archivo))
        if encontrados:
            return encontrados[0]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
