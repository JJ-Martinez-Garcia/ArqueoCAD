"""Coloca el aviso de licencia GPL en los archivos fuente.

La GPL no obliga a marcar cada archivo, pero sí lo recomienda: sin el aviso, un
archivo que circule suelto no lleva consigo la información de bajo qué
condiciones puede usarse.

El aviso se inserta después del docstring del módulo, para no desplazarlo de la
primera posición —donde Python espera encontrarlo— y para que la documentación
siga siendo lo primero que se lee.

    .venv\\Scripts\\python.exe tools/poner_cabeceras.py [--comprobar]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: Marca que permite reconocer un aviso ya puesto y no duplicarlo.
MARCA = "Parte de ArqueoCAD"

AVISO = f"""# {MARCA}. Copyright (C) 2026 José Javier Martínez García
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
"""

#: Carpetas cuyos archivos llevan el aviso. Las pruebas también: forman parte
#: del programa y se distribuyen con el código fuente.
CARPETAS = ("src", "tools", "tests")


def archivos() -> list[Path]:
    encontrados: list[Path] = []
    for carpeta in CARPETAS:
        encontrados.extend(sorted((RAIZ / carpeta).rglob("*.py")))
    return encontrados


def insertar(texto: str) -> str | None:
    """Devuelve el texto con el aviso puesto, o None si ya lo tenía."""
    if MARCA in texto:
        return None

    lineas = texto.splitlines(keepends=True)

    # Se localiza el final del docstring del módulo para colocar el aviso justo
    # después: el docstring debe seguir siendo la primera instrucción.
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return None

    corte = 0
    if arbol.body and isinstance(arbol.body[0], ast.Expr):
        valor = arbol.body[0].value
        if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            corte = valor.end_lineno or 0

    cabecera = "".join(lineas[:corte])
    resto = "".join(lineas[corte:])

    if corte:
        return f"{cabecera}\n{AVISO}{resto}"
    return f"{AVISO}\n{resto}"


def main() -> int:
    solo_comprobar = "--comprobar" in sys.argv

    puestos = 0
    ya_tenian = 0

    for ruta in archivos():
        texto = ruta.read_text(encoding="utf-8")
        nuevo = insertar(texto)

        if nuevo is None:
            ya_tenian += 1
            continue

        puestos += 1
        if solo_comprobar:
            print(f"  falta en {ruta.relative_to(RAIZ)}")
        else:
            ruta.write_text(nuevo, encoding="utf-8")
            print(f"  {ruta.relative_to(RAIZ)}")

    total = puestos + ya_tenian
    if solo_comprobar:
        print(f"\n{ya_tenian} de {total} archivos con aviso.")
        return 1 if puestos else 0

    print(f"\nAviso puesto en {puestos} archivos; {ya_tenian} ya lo tenían.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
