"""Modelo interno neutro de ArqueoCAD.

Todo lo que entra en la aplicación (DXF, DWG o SVG) se traduce a estas
estructuras, y todo lo que sale se genera a partir de ellas. Así el número de
conversores crece de forma lineal con los formatos y no de forma cuadrática.

Conviene distinguir dos representaciones que conviven en un mismo `Documento`:

- Las **primitivas aplanadas** (`Polilinea`, `Texto`, `Punto`, `Relleno`) son
  una simplificación pensada para dibujar rápido en pantalla y para exportar a
  SVG. Las curvas ya vienen convertidas en segmentos rectos.
- El **documento de origen** (`origen_ezdxf`) se conserva intacto. La
  exportación a DXF copia de él las entidades originales, de modo que splines,
  sombreados y bloques llegan al archivo de salida sin pérdida. Reconstruirlos
  desde las primitivas aplanadas degradaría el dibujo.
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
from typing import Any, Iterable, Sequence

from .geometria import Extension, Punto2D
from .unidades import Unidad


#: Capa donde AutoCAD deposita los puntos de definición de las cotas. Nunca se
#: imprime, y arrastrarla a la exportación ensucia el archivo de salida con
#: geometría que el usuario no dibujó.
NOMBRE_DEFPOINTS = "defpoints"

#: Separación entre líneas de un MTEXT, en múltiplos de la altura del carácter.
#: Es el valor que aplica AutoCAD cuando el texto no declara uno propio.
INTERLINEADO_MTEXT = 5 / 3


class FormatoOrigen(str, Enum):
    """Formato del archivo tal como lo entregó el usuario."""

    DXF = "dxf"
    DWG = "dwg"
    SVG = "svg"
    #: Imagen vectorizada. A diferencia del resto, su geometría no se ha leído
    #: sino deducido, de modo que siempre conviene revisarla.
    RASTER = "raster"


@dataclass(slots=True)
class Capa:
    """Una capa del dibujo.

    El color se guarda ya resuelto a RGB para no tener que consultar la tabla
    de colores de AutoCAD en cada repintado del visor.
    """

    nombre: str
    color: tuple[int, int, int] = (255, 255, 255)
    aci: int = 7
    visible: bool = True
    congelada: bool = False
    bloqueada: bool = False
    tipo_linea: str = "Continuous"
    grosor: float = 0.0

    #: Las capas no imprimibles quedan fuera de la exportación por defecto. Es
    #: el caso de «Defpoints», donde AutoCAD guarda los puntos de definición de
    #: las cotas: se ven en pantalla, pero no forman parte del dibujo.
    imprimible: bool = True

    #: Se rellena al terminar la lectura; alimenta el panel de capas.
    n_entidades: int = 0
    tipos_presentes: set[str] = field(default_factory=set)

    @property
    def dibujable(self) -> bool:
        """Una capa congelada no se dibuja aunque esté marcada como visible."""
        return self.visible and not self.congelada

    @property
    def auxiliar(self) -> bool:
        """Capa de servicio del programa de CAD, no contenido del plano."""
        return not self.imprimible or self.nombre.casefold() == NOMBRE_DEFPOINTS


@dataclass(slots=True)
class Entidad:
    """Base de las primitivas de presentación.

    `color` a ``None`` significa «por capa», que es el caso mayoritario en los
    dibujos de excavación y conviene no resolver hasta el momento de pintar.
    """

    capa: str
    color: tuple[int, int, int] | None = None
    handle: str = ""
    tipo_origen: str = ""

    def extension(self) -> Extension:  # pragma: no cover - contrato abstracto
        raise NotImplementedError


@dataclass(slots=True)
class Polilinea(Entidad):
    """Cadena de segmentos rectos.

    Absorbe LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC, ELLIPSE y SPLINE: todas
    acaban aplanadas aquí con la tolerancia configurada.
    """

    puntos: list[Punto2D] = field(default_factory=list)
    cerrada: bool = False

    def extension(self) -> Extension:
        return Extension.desde_puntos(self.puntos)


@dataclass(slots=True)
class Punto(Entidad):
    """Entidad POINT. Se dibuja como una marca de tamaño fijo en pantalla."""

    posicion: Punto2D = (0.0, 0.0)

    def extension(self) -> Extension:
        return Extension.desde_puntos([self.posicion])


@dataclass(slots=True)
class Texto(Entidad):
    """TEXT y MTEXT resueltos a texto plano.

    `contenido` puede traer saltos de línea: un MTEXT es con frecuencia un
    párrafo, y concatenar sus líneas produciría rótulos ilegibles del tipo
    «Sector ACampaña 2026».

    La fuente original no se conserva: al exportar a SVG se sustituye por una
    fuente del sistema, y esa sustitución se advierte en el informe de
    conversión en lugar de silenciarse.
    """

    contenido: str = ""
    posicion: Punto2D = (0.0, 0.0)
    altura: float = 1.0
    rotacion: float = 0.0
    anclaje: str = "izquierda-abajo"

    #: Separación entre líneas, en múltiplos de la altura del carácter.
    interlineado: float = INTERLINEADO_MTEXT

    @property
    def lineas(self) -> list[str]:
        return self.contenido.split("\n")

    @property
    def multilinea(self) -> bool:
        return "\n" in self.contenido

    def extension(self) -> Extension:
        # Aproximación deliberadamente generosa: sin métricas de fuente no se
        # puede medir el texto con exactitud, y quedarse corto recortaría el
        # encuadre automático.
        lineas = self.lineas
        ancho = self.altura * 0.6 * max((len(l) for l in lineas), default=1)
        alto = self.altura * (1 + (len(lineas) - 1) * self.interlineado)
        x, y = self.posicion
        # Las líneas siguientes de un párrafo se escriben por debajo de la
        # primera, de modo que la envolvente crece hacia abajo.
        return Extension(x, y - (alto - self.altura), x + ancho, y + self.altura)


@dataclass(slots=True)
class Relleno(Entidad):
    """HATCH y SOLID reducidos a sus contornos.

    Los patrones de sombreado de AutoCAD no tienen equivalente en SVG. Se
    conserva el contorno y, si el relleno era sólido, se marca para poder
    pintarlo; el patrón concreto se pierde y así se informa.
    """

    contornos: list[list[Punto2D]] = field(default_factory=list)
    solido: bool = False
    patron: str = ""

    def extension(self) -> Extension:
        return Extension.union(
            Extension.desde_puntos(c) for c in self.contornos
        )


@dataclass(slots=True)
class Aviso:
    """Incidencia detectada durante la lectura o la escritura.

    El criterio es no callar ninguna pérdida de información: es preferible un
    aviso de más que un plano que llega alterado a la publicación.
    """

    nivel: str  # "info" | "aviso" | "error"
    mensaje: str
    detalle: str = ""


@dataclass
class Documento:
    """Un plano cargado en memoria."""

    ruta: str
    formato: FormatoOrigen
    unidad: Unidad = Unidad.SIN_DEFINIR
    capas: dict[str, Capa] = field(default_factory=dict)
    entidades: list[Entidad] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)

    #: Documento ezdxf original, cuando el origen lo tiene. Es la fuente de
    #: verdad para exportar a DXF sin pérdida.
    origen_ezdxf: Any = None

    #: Ruta del DXF intermedio cuando el original era DWG, para poder
    #: informar al usuario de qué se ha leído realmente.
    ruta_intermedia: str | None = None

    _extension: Extension | None = field(default=None, repr=False)

    def capa(self, nombre: str) -> Capa:
        """Devuelve la capa, creándola si el archivo la referencia sin declararla.

        Ocurre con cierta frecuencia en DXF generados por programas de terceros
        y en los procedentes de conversión desde DWG.
        """
        capa = self.capas.get(nombre)
        if capa is None:
            capa = Capa(nombre=nombre)
            self.capas[nombre] = capa
            self.avisos.append(
                Aviso(
                    "aviso",
                    f"La capa «{nombre}» se usa pero no está declarada en la tabla de capas.",
                    "Se ha creado con los valores por defecto.",
                )
            )
        return capa

    def extension(self) -> Extension:
        """Envolvente de todo el dibujo, calculada una sola vez."""
        if self._extension is None:
            self._extension = Extension.union(e.extension() for e in self.entidades)
        return self._extension

    def entidades_de(self, capas: Iterable[str]) -> list[Entidad]:
        seleccion = set(capas)
        return [e for e in self.entidades if e.capa in seleccion]

    def extension_de_capa(self, *capas: str) -> Extension:
        """Envolvente de las capas indicadas, para encuadrar o comprobar escala."""
        return Extension.union(e.extension() for e in self.entidades_de(capas))

    def nombres_de_capa(self) -> list[str]:
        """Nombres ordenados de forma natural.

        El orden natural importa: con nomenclaturas de excavación del tipo
        ``UE-2``, ``UE-10``, ``UE-101`` el orden alfabético las desordena.
        """
        return sorted(self.capas, key=_clave_natural)

    def recalcular_estadisticas(self) -> None:
        """Recuenta entidades por capa. Se llama al terminar cada lectura."""
        for capa in self.capas.values():
            capa.n_entidades = 0
            capa.tipos_presentes = set()
        for entidad in self.entidades:
            capa = self.capa(entidad.capa)
            capa.n_entidades += 1
            if entidad.tipo_origen:
                capa.tipos_presentes.add(entidad.tipo_origen)


def _clave_natural(texto: str) -> tuple:
    """Trocea el nombre en texto y números para ordenar UE-2 antes que UE-10."""
    import re

    partes = re.split(r"(\d+)", texto.casefold())
    return tuple(int(p) if p.isdigit() else p for p in partes)
