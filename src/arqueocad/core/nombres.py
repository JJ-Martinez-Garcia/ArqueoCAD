"""Conversión de nombres de capa en nombres de archivo.

Los nombres de capa de excavación traen acentos y espacios —«SARCÓFAGO_2024»,
«PERÍMETRO_EXCAVADO_2024», «TEXTO 2024»— y los tres sistemas operativos los
admiten sin problema, de modo que se conservan.

Lo que **no** se hace es despojar de tildes: en un mismo plano coexisten
`PERIMETRO_TUMBA_2024` y `PERÍMETRO_EXCAVADO_2024`, y esa clase de saneo acaba
fundiendo capas distintas en un mismo archivo. Solo se sustituye lo que el
sistema de archivos prohíbe de verdad, y cualquier colisión se resuelve con
sufijo numérico.
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

import re

#: Caracteres que Windows prohíbe en un nombre de archivo. Es el conjunto más
#: restrictivo de los tres sistemas, así que aplicarlo siempre garantiza que un
#: archivo generado en Linux se pueda abrir en Windows.
_PROHIBIDOS = r'[<>:"/\\|?*]'

#: Nombres reservados por Windows, que no admite ni siquiera con extensión.
_RESERVADOS = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

#: Margen frente al límite de ruta de Windows. El nombre de capa comparte
#: presupuesto con la carpeta de destino y el prefijo del plano.
LONGITUD_MAXIMA = 100


def sanear(nombre: str) -> str:
    """Convierte un nombre de capa en un fragmento de nombre de archivo válido.

    Conserva acentos, eñes y espacios; sustituye por guion bajo los caracteres
    prohibidos y los de control.
    """
    limpio = re.sub(_PROHIBIDOS, "_", nombre)
    limpio = "".join("_" if ord(c) < 32 else c for c in limpio)

    # Windows descarta los espacios y puntos finales al crear el archivo, lo
    # que produce nombres distintos de los pedidos.
    limpio = limpio.strip(" .")

    if not limpio:
        limpio = "capa_sin_nombre"

    if limpio.split(".")[0].casefold() in _RESERVADOS:
        limpio = f"_{limpio}"

    if len(limpio) > LONGITUD_MAXIMA:
        limpio = limpio[:LONGITUD_MAXIMA].rstrip(" .")

    return limpio


def unicos(nombres: list[str]) -> dict[str, str]:
    """Asigna a cada nombre de capa un nombre de archivo distinto.

    Devuelve la correspondencia entre el nombre original y el saneado. Cuando
    dos capas se sanean al mismo texto —caso posible si difieren solo en un
    carácter prohibido—, la segunda recibe un sufijo numérico.
    """
    asignados: dict[str, str] = {}
    usados: set[str] = set()

    for nombre in nombres:
        base = sanear(nombre)
        candidato = base
        contador = 2
        # La comparación va en minúsculas porque Windows y macOS no distinguen
        # mayúsculas: «MUROS» y «Muros» se pisarían el archivo.
        while candidato.casefold() in usados:
            candidato = f"{base}_{contador}"
            contador += 1
        usados.add(candidato.casefold())
        asignados[nombre] = candidato

    return asignados
