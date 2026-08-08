"""Separación de un plano en varios archivos por capas.

Es la función que motiva la aplicación. Coordina el recorrido de las capas, el
nombrado de los archivos y la llamada a los escritores, y devuelve un informe de
lo generado que permita comprobar el resultado sin abrir los archivos uno a uno.
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

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from .modelo import Aviso, Documento
from .nombres import unicos
from .unidades import Unidad


class Modo(str, Enum):
    """Cómo se reparte el plano entre archivos."""

    #: Un archivo por cada capa seleccionada.
    POR_CAPA = "por_capa"
    #: Un archivo por grupo de capas definido por el usuario.
    POR_GRUPO = "por_grupo"
    #: Un único archivo con todas las capas seleccionadas.
    UNICO = "unico"


class Formato(str, Enum):
    DXF = "dxf"
    SVG = "svg"


@dataclass
class Opciones:
    """Ajustes de una separación."""

    carpeta: Path
    modo: Modo = Modo.POR_CAPA
    formatos: tuple[Formato, ...] = (Formato.DXF,)

    #: Prefijo de los archivos. Si se omite, se usa el nombre del plano.
    prefijo: str = ""

    #: Grupos de capas, usados solo en `Modo.POR_GRUPO`.
    grupos: dict[str, list[str]] = field(default_factory=dict)

    explotar_bloques: bool = False
    version_dxf: str | None = None

    escala_svg: float = 1.0
    unidad_forzada: Unidad | None = None

    #: Las capas auxiliares del programa de CAD («Defpoints» y las marcadas
    #: como no imprimibles) se descartan salvo petición expresa.
    incluir_auxiliares: bool = False

    #: Una capa sin entidades genera un archivo vacío, que rara vez interesa.
    omitir_vacias: bool = True


@dataclass
class ArchivoGenerado:
    ruta: Path
    formato: Formato
    capas: list[str]
    n_entidades: int
    tamanio: int = 0


@dataclass
class Resultado:
    archivos: list[ArchivoGenerado] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)
    omitidas: list[str] = field(default_factory=list)

    @property
    def total_archivos(self) -> int:
        return len(self.archivos)

    @property
    def hubo_problemas(self) -> bool:
        return any(a.nivel == "error" for a in self.avisos)


def separar(
    documento: Documento,
    capas: Iterable[str],
    opciones: Opciones,
    progreso: Callable[[int, int, str], None] | None = None,
) -> Resultado:
    """Ejecuta la separación y devuelve el informe de lo generado.

    Args:
        documento: plano de partida.
        capas: capas seleccionadas por el usuario.
        opciones: ajustes de la separación.
        progreso: función que recibe (hechos, total, descripción) para poder
            informar del avance sin que la interfaz se quede sin respuesta.
    """
    from ..io.escritor_dxf import EscrituraDXFError, escribir_dxf
    from ..io.escritor_svg import EscrituraSVGError, escribir_svg

    resultado = Resultado()
    seleccion = _filtrar(documento, capas, opciones, resultado)
    if not seleccion:
        resultado.avisos.append(
            Aviso("error", "No queda ninguna capa que exportar tras aplicar los filtros.")
        )
        return resultado

    prefijo = opciones.prefijo or Path(documento.ruta).stem
    lotes = _lotes(seleccion, opciones, prefijo)

    total = len(lotes) * len(opciones.formatos)
    hechos = 0

    for etiqueta, capas_del_lote in lotes:
        n_entidades = sum(
            documento.capas[c].n_entidades for c in capas_del_lote if c in documento.capas
        )

        for formato in opciones.formatos:
            destino = opciones.carpeta / f"{etiqueta}.{formato.value}"
            if progreso is not None:
                progreso(hechos, total, destino.name)

            try:
                if formato is Formato.DXF:
                    avisos = escribir_dxf(
                        documento,
                        capas_del_lote,
                        destino,
                        explotar_bloques=opciones.explotar_bloques,
                        version=opciones.version_dxf,
                    )
                else:
                    avisos = escribir_svg(
                        documento,
                        capas_del_lote,
                        destino,
                        escala=opciones.escala_svg,
                        unidad_forzada=opciones.unidad_forzada,
                    )
            except (EscrituraDXFError, EscrituraSVGError) as exc:
                resultado.avisos.append(
                    Aviso("error", f"No se ha podido generar «{destino.name}».", str(exc))
                )
                hechos += 1
                continue

            resultado.avisos.extend(avisos)
            resultado.archivos.append(
                ArchivoGenerado(
                    ruta=destino,
                    formato=formato,
                    capas=list(capas_del_lote),
                    n_entidades=n_entidades,
                    tamanio=destino.stat().st_size if destino.is_file() else 0,
                )
            )
            hechos += 1

    if progreso is not None:
        progreso(total, total, "")

    return resultado


def _filtrar(
    documento: Documento,
    capas: Iterable[str],
    opciones: Opciones,
    resultado: Resultado,
) -> list[str]:
    """Descarta las capas que no deben exportarse, dejando constancia."""
    seleccion: list[str] = []

    for nombre in capas:
        capa = documento.capas.get(nombre)
        if capa is None:
            continue

        if capa.auxiliar and not opciones.incluir_auxiliares:
            resultado.omitidas.append(nombre)
            continue

        if capa.n_entidades == 0 and opciones.omitir_vacias:
            resultado.omitidas.append(nombre)
            continue

        seleccion.append(nombre)

    if resultado.omitidas:
        resultado.avisos.append(
            Aviso(
                "info",
                f"{len(resultado.omitidas)} capas se han dejado fuera por estar vacías "
                "o ser auxiliares del programa de CAD.",
                ", ".join(resultado.omitidas),
            )
        )

    return seleccion


def _lotes(
    seleccion: list[str], opciones: Opciones, prefijo: str
) -> list[tuple[str, list[str]]]:
    """Reparte las capas en lotes, cada uno con su nombre de archivo."""
    if opciones.modo is Modo.UNICO:
        return [(prefijo, seleccion)]

    if opciones.modo is Modo.POR_GRUPO:
        etiquetas = unicos(list(opciones.grupos))
        lotes = []
        for grupo, capas_grupo in opciones.grupos.items():
            del_grupo = [c for c in capas_grupo if c in seleccion]
            if del_grupo:
                lotes.append((f"{prefijo}_{etiquetas[grupo]}", del_grupo))
        return lotes

    etiquetas = unicos(seleccion)
    return [(f"{prefijo}_{etiquetas[nombre]}", [nombre]) for nombre in seleccion]
