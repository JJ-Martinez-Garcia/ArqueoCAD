"""Medición de distancias y superficies sobre el plano.

Las medidas se dan en las unidades declaradas por el dibujo. Cuando el plano no
las declara, se expresan en unidades de dibujo y se dice así: presentar «12,4 m»
sobre un plano de escala desconocida sería inventar un dato.
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

import math
from dataclasses import dataclass, field

from .geometria import Punto2D
from .unidades import Unidad, factor_a_metros
from .unidades import simbolo as simbolo_unidad


@dataclass
class Medicion:
    """Serie de puntos marcados sobre el plano y las magnitudes que definen."""

    puntos: list[Punto2D] = field(default_factory=list)
    unidad: Unidad = Unidad.SIN_DEFINIR

    def anadir(self, punto: Punto2D) -> None:
        self.puntos.append(punto)

    def deshacer(self) -> None:
        if self.puntos:
            self.puntos.pop()

    def limpiar(self) -> None:
        self.puntos.clear()

    @property
    def activa(self) -> bool:
        return bool(self.puntos)

    @property
    def longitud(self) -> float:
        """Recorrido total de la polilínea marcada."""
        return sum(
            math.dist(self.puntos[i], self.puntos[i + 1])
            for i in range(len(self.puntos) - 1)
        )

    @property
    def ultimo_tramo(self) -> float:
        if len(self.puntos) < 2:
            return 0.0
        return math.dist(self.puntos[-2], self.puntos[-1])

    @property
    def area(self) -> float:
        """Superficie encerrada, cerrando la figura entre el último punto y el primero.

        Se calcula por la fórmula del cordón de zapato y se devuelve en valor
        absoluto, de modo que el sentido de marcado no altere el resultado.
        """
        if len(self.puntos) < 3:
            return 0.0

        total = 0.0
        n = len(self.puntos)
        for i in range(n):
            x0, y0 = self.puntos[i]
            x1, y1 = self.puntos[(i + 1) % n]
            total += x0 * y1 - x1 * y0
        return abs(total) / 2

    @property
    def perimetro(self) -> float:
        """Longitud del contorno cerrado."""
        if len(self.puntos) < 3:
            return self.longitud
        return self.longitud + math.dist(self.puntos[-1], self.puntos[0])

    @property
    def acimut(self) -> float | None:
        """Rumbo del último tramo en grados, medido desde el norte y hacia el este.

        Es la convención topográfica, no la matemática: en un plano de
        excavación interesa la orientación de un muro respecto al norte.
        """
        if len(self.puntos) < 2:
            return None
        (x0, y0), (x1, y1) = self.puntos[-2], self.puntos[-1]
        if math.isclose(x0, x1) and math.isclose(y0, y1):
            return None
        angulo = math.degrees(math.atan2(x1 - x0, y1 - y0))
        return angulo % 360

    # -- presentación ----------------------------------------------------

    def texto_longitud(self) -> str:
        return _formatear(self.longitud, self.unidad)

    def texto_area(self) -> str:
        return _formatear_area(self.area, self.unidad)

    def resumen(self) -> str:
        """Línea de estado con lo que procede según los puntos marcados."""
        if not self.puntos:
            return "Medición: marque el primer punto"

        if len(self.puntos) == 1:
            return "Medición: marque el segundo punto"

        partes = [f"Longitud: {self.texto_longitud()}"]

        acimut = self.acimut
        if acimut is not None:
            partes.append(f"Acimut: {acimut:.1f}°")

        if len(self.puntos) >= 3:
            partes.append(f"Área: {self.texto_area()}")
            partes.append(f"Perímetro: {_formatear(self.perimetro, self.unidad)}")

        return "   ·   ".join(partes)


def _formatear(valor: float, unidad: Unidad) -> str:
    """Escribe una longitud eligiendo el múltiplo más legible."""
    simbolo = simbolo_unidad(unidad)
    factor = factor_a_metros(unidad)

    if factor is None:
        return f"{valor:,.3f} ud.".replace(",", " ")

    metros = valor * factor
    if metros >= 1000:
        return f"{metros / 1000:,.3f} km".replace(",", " ")
    if metros >= 1:
        return f"{metros:,.3f} m".replace(",", " ")
    if metros >= 0.01:
        return f"{metros * 100:,.2f} cm".replace(",", " ")
    return f"{metros * 1000:,.1f} mm".replace(",", " ")


def _formatear_area(valor: float, unidad: Unidad) -> str:
    simbolo = simbolo_unidad(unidad)
    factor = factor_a_metros(unidad)

    if factor is None:
        return f"{valor:,.3f} ud.²".replace(",", " ")

    metros2 = valor * factor * factor
    if metros2 >= 10_000:
        return f"{metros2 / 10_000:,.4f} ha".replace(",", " ")
    if metros2 >= 1:
        return f"{metros2:,.3f} m²".replace(",", " ")
    return f"{metros2 * 10_000:,.1f} cm²".replace(",", " ")
