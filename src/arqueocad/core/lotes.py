"""Separación de varios planos en una sola pasada.

Es la función que distingue el trabajo de campaña del trabajo de un plano
suelto: los planos de una excavación comparten nomenclatura de capas, y
separarlos uno a uno repitiendo las mismas opciones veinte veces es donde se va
el tiempo.

El filtro de capas admite comodines —``UE-*``, ``*_2024``, ``MURO*``— porque en
un lote no se sabe de antemano qué capas trae cada archivo, pero sí qué familias
interesan.
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

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .modelo import Aviso, Documento
from .nombres import sanear
from .separador import ArchivoGenerado, Opciones, Resultado, separar


@dataclass
class OpcionesLote:
    """Ajustes que se aplican a todos los planos del lote."""

    #: Ajustes de separación. La carpeta que traiga se usa como raíz.
    separacion: Opciones

    #: Patrones de capa, con comodines. Vacío significa todas las capas.
    patrones: list[str] = field(default_factory=list)

    #: Si cada plano recibe su propia subcarpeta. Con muchos planos evita
    #: reunir cientos de archivos en un mismo sitio.
    subcarpeta_por_plano: bool = True

    #: Un plano que falla no debe interrumpir el resto de la campaña.
    continuar_tras_error: bool = True


@dataclass
class ResultadoPlano:
    """Lo ocurrido con un plano concreto del lote."""

    ruta: Path
    correcto: bool
    n_capas: int = 0
    n_entidades: int = 0
    archivos: list[ArchivoGenerado] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)
    error: str = ""


@dataclass
class ResultadoLote:
    planos: list[ResultadoPlano] = field(default_factory=list)

    @property
    def correctos(self) -> list[ResultadoPlano]:
        return [p for p in self.planos if p.correcto]

    @property
    def fallidos(self) -> list[ResultadoPlano]:
        return [p for p in self.planos if not p.correcto]

    @property
    def total_archivos(self) -> int:
        return sum(len(p.archivos) for p in self.correctos)

    def resumen(self) -> str:
        partes = [
            f"{len(self.correctos)} de {len(self.planos)} planos procesados",
            f"{self.total_archivos} archivos generados",
        ]
        if self.fallidos:
            partes.append(f"{len(self.fallidos)} con errores")
        return " · ".join(partes)


def capas_que_encajan(documento: Documento, patrones: Sequence[str]) -> list[str]:
    """Capas del documento que casan con alguno de los patrones.

    Sin patrones devuelve todas. La comparación no distingue mayúsculas, porque
    la nomenclatura de campo rara vez es constante en ese punto.
    """
    nombres = documento.nombres_de_capa()
    if not patrones:
        return nombres

    seleccion = []
    for nombre in nombres:
        plegado = nombre.casefold()
        if any(fnmatch.fnmatch(plegado, p.casefold()) for p in patrones):
            seleccion.append(nombre)
    return seleccion


def procesar_lote(
    rutas: Iterable[str | Path],
    opciones: OpcionesLote,
    progreso: Callable[[int, int, str], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> ResultadoLote:
    """Separa cada plano del lote con las mismas opciones.

    Args:
        rutas: planos a procesar.
        opciones: ajustes comunes.
        progreso: recibe (hechos, total, nombre del plano en curso).
        cancelado: se consulta entre planos; si devuelve cierto, se detiene.
    """
    from ..io import leer

    lista = [Path(r) for r in rutas]
    resultado = ResultadoLote()
    raiz = opciones.separacion.carpeta

    for indice, ruta in enumerate(lista):
        if cancelado is not None and cancelado():
            break

        if progreso is not None:
            progreso(indice, len(lista), ruta.name)

        try:
            documento = leer(ruta)
        except Exception as exc:  # noqa: BLE001 - un plano roto no para la campaña
            resultado.planos.append(
                ResultadoPlano(ruta=ruta, correcto=False, error=str(exc))
            )
            if not opciones.continuar_tras_error:
                break
            continue

        capas = capas_que_encajan(documento, opciones.patrones)
        if not capas:
            resultado.planos.append(
                ResultadoPlano(
                    ruta=ruta,
                    correcto=False,
                    error="Ninguna capa del plano casa con los patrones indicados.",
                )
            )
            continue

        destino = raiz / sanear(ruta.stem) if opciones.subcarpeta_por_plano else raiz
        ajustes = _ajustes_para(opciones.separacion, destino, ruta)

        try:
            parcial: Resultado = separar(documento, capas, ajustes)
        except Exception as exc:  # noqa: BLE001
            resultado.planos.append(
                ResultadoPlano(ruta=ruta, correcto=False, error=str(exc))
            )
            if not opciones.continuar_tras_error:
                break
            continue

        resultado.planos.append(
            ResultadoPlano(
                ruta=ruta,
                correcto=not parcial.hubo_problemas,
                n_capas=len(capas),
                n_entidades=len(documento.entidades),
                archivos=parcial.archivos,
                avisos=parcial.avisos,
                error="" if not parcial.hubo_problemas else _primer_error(parcial),
            )
        )

    if progreso is not None:
        progreso(len(lista), len(lista), "")

    return resultado


def _ajustes_para(base: Opciones, destino: Path, plano: Path) -> Opciones:
    """Copia los ajustes cambiando carpeta y prefijo para este plano."""
    from dataclasses import replace

    # El prefijo se toma del nombre de cada plano: sin esto, todos los archivos
    # del lote se llamarían igual y se pisarían al compartir carpeta.
    return replace(base, carpeta=destino, prefijo=base.prefijo or plano.stem)


def _primer_error(resultado: Resultado) -> str:
    for aviso in resultado.avisos:
        if aviso.nivel == "error":
            return aviso.mensaje
    return ""
