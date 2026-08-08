"""Tipos geométricos y utilidades de aplanado.

El aplanado convierte curvas en cadenas de segmentos rectos. Es una operación
con pérdida, gobernada por una tolerancia expresada en unidades de dibujo: la
distancia máxima admitida entre la curva real y la poligonal que la sustituye.
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
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

Punto2D = tuple[float, float]

#: Tolerancia por defecto, en unidades de dibujo. Con planos en metros supone
#: medio milímetro; con planos en milímetros, media micra. El visor la ajusta
#: al nivel de zoom para no aplanar de más.
TOLERANCIA_POR_DEFECTO = 0.0005

#: Cotas de seguridad para que una tolerancia mal elegida no genere millones de
#: segmentos ni un círculo de cuatro lados.
MIN_SEGMENTOS_ARCO = 8
MAX_SEGMENTOS_ARCO = 720


@dataclass(frozen=True, slots=True)
class Extension:
    """Rectángulo envolvente alineado con los ejes."""

    x_min: float = math.inf
    y_min: float = math.inf
    x_max: float = -math.inf
    y_max: float = -math.inf

    @property
    def vacia(self) -> bool:
        return self.x_min > self.x_max or self.y_min > self.y_max

    @property
    def ancho(self) -> float:
        return 0.0 if self.vacia else self.x_max - self.x_min

    @property
    def alto(self) -> float:
        return 0.0 if self.vacia else self.y_max - self.y_min

    @property
    def centro(self) -> Punto2D:
        if self.vacia:
            return (0.0, 0.0)
        return ((self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2)

    @classmethod
    def desde_puntos(cls, puntos: Sequence[Punto2D] | Iterable[Punto2D]) -> Extension:
        x_min = y_min = math.inf
        x_max = y_max = -math.inf
        for x, y in puntos:
            if x < x_min:
                x_min = x
            if x > x_max:
                x_max = x
            if y < y_min:
                y_min = y
            if y > y_max:
                y_max = y
        return cls(x_min, y_min, x_max, y_max)

    @classmethod
    def union(cls, extensiones: Iterable[Extension]) -> Extension:
        x_min = y_min = math.inf
        x_max = y_max = -math.inf
        for e in extensiones:
            if e.vacia:
                continue
            x_min = min(x_min, e.x_min)
            y_min = min(y_min, e.y_min)
            x_max = max(x_max, e.x_max)
            y_max = max(y_max, e.y_max)
        return cls(x_min, y_min, x_max, y_max)

    def intersecta(self, otra: Extension) -> bool:
        """Prueba usada por el visor para descartar lo que queda fuera de pantalla."""
        if self.vacia or otra.vacia:
            return False
        return not (
            self.x_max < otra.x_min
            or self.x_min > otra.x_max
            or self.y_max < otra.y_min
            or self.y_min > otra.y_max
        )

    def expandida(self, margen: float) -> Extension:
        if self.vacia:
            return self
        return Extension(
            self.x_min - margen,
            self.y_min - margen,
            self.x_max + margen,
            self.y_max + margen,
        )


def segmentos_para_arco(radio: float, angulo_barrido: float, tolerancia: float) -> int:
    """Número de segmentos que mantiene el error de flecha bajo la tolerancia.

    Para un arco dividido en ``n`` segmentos, la flecha vale
    ``r · (1 − cos(θ / 2n))``. Se despeja ``n`` e imponen las cotas de
    seguridad.
    """
    if radio <= 0 or angulo_barrido <= 0:
        return MIN_SEGMENTOS_ARCO
    if tolerancia <= 0 or tolerancia >= radio:
        return MIN_SEGMENTOS_ARCO

    try:
        paso = 2 * math.acos(1 - tolerancia / radio)
    except ValueError:
        return MIN_SEGMENTOS_ARCO
    if paso <= 0:
        return MAX_SEGMENTOS_ARCO

    n = math.ceil(angulo_barrido / paso)
    return max(MIN_SEGMENTOS_ARCO, min(n, MAX_SEGMENTOS_ARCO))


def aplanar_arco(
    centro: Punto2D,
    radio: float,
    inicio: float,
    fin: float,
    tolerancia: float = TOLERANCIA_POR_DEFECTO,
) -> list[Punto2D]:
    """Aplana un arco. Los ángulos van en radianes y en sentido antihorario."""
    barrido = fin - inicio
    while barrido <= 0:
        barrido += 2 * math.pi

    n = segmentos_para_arco(radio, barrido, tolerancia)
    cx, cy = centro
    paso = barrido / n
    return [
        (cx + radio * math.cos(inicio + i * paso), cy + radio * math.sin(inicio + i * paso))
        for i in range(n + 1)
    ]


def aplanar_bulge(
    inicio: Punto2D, fin: Punto2D, bulge: float, tolerancia: float = TOLERANCIA_POR_DEFECTO
) -> list[Punto2D]:
    """Aplana el tramo curvo de una polilínea definido por su *bulge*.

    El *bulge* de AutoCAD es la tangente de un cuarto del ángulo barrido; su
    signo indica el sentido de giro. Devuelve los puntos intermedios, sin
    repetir los extremos, para poder encadenar tramos sin duplicar vértices.
    """
    if abs(bulge) < 1e-12:
        return []

    x0, y0 = inicio
    x1, y1 = fin
    cuerda = math.hypot(x1 - x0, y1 - y0)
    if cuerda < 1e-12:
        return []

    angulo = 4 * math.atan(bulge)
    radio = cuerda / (2 * math.sin(abs(angulo) / 2))

    # Centro: se parte del punto medio de la cuerda y se desplaza por su
    # mediatriz una distancia igual a la apotema.
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    apotema = math.sqrt(max(radio * radio - (cuerda / 2) ** 2, 0.0))
    dx, dy = (x1 - x0) / cuerda, (y1 - y0) / cuerda
    signo = 1.0 if angulo > 0 else -1.0
    cx, cy = mx - signo * apotema * dy, my + signo * apotema * dx

    a0 = math.atan2(y0 - cy, x0 - cx)
    n = segmentos_para_arco(radio, abs(angulo), tolerancia)
    paso = angulo / n
    return [
        (cx + radio * math.cos(a0 + i * paso), cy + radio * math.sin(a0 + i * paso))
        for i in range(1, n)
    ]


def aplanar_bezier_cubica(
    p0: Punto2D, p1: Punto2D, p2: Punto2D, p3: Punto2D, tolerancia: float
) -> Iterator[Punto2D]:
    """Aplana una Bézier cúbica por subdivisión adaptativa.

    Se usa al leer SVG, donde las curvas llegan como Béziers. Devuelve los
    puntos intermedios sin incluir ``p0`` ni ``p3``.
    """
    yield from _subdividir_bezier(p0, p1, p2, p3, tolerancia, 0)


_PROFUNDIDAD_MAXIMA = 16


def _subdividir_bezier(
    p0: Punto2D, p1: Punto2D, p2: Punto2D, p3: Punto2D, tolerancia: float, nivel: int
) -> Iterator[Punto2D]:
    if nivel >= _PROFUNDIDAD_MAXIMA or _bezier_es_plana(p0, p1, p2, p3, tolerancia):
        return

    # Subdivisión de De Casteljau en el parámetro medio.
    p01 = _medio(p0, p1)
    p12 = _medio(p1, p2)
    p23 = _medio(p2, p3)
    p012 = _medio(p01, p12)
    p123 = _medio(p12, p23)
    medio = _medio(p012, p123)

    yield from _subdividir_bezier(p0, p01, p012, medio, tolerancia, nivel + 1)
    yield medio
    yield from _subdividir_bezier(medio, p123, p23, p3, tolerancia, nivel + 1)


def _medio(a: Punto2D, b: Punto2D) -> Punto2D:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _bezier_es_plana(p0: Punto2D, p1: Punto2D, p2: Punto2D, p3: Punto2D, tolerancia: float) -> bool:
    """Mide cuánto se separan los puntos de control de la cuerda extremo a extremo."""
    return max(
        _distancia_a_recta(p1, p0, p3),
        _distancia_a_recta(p2, p0, p3),
    ) <= tolerancia


def _distancia_a_recta(p: Punto2D, a: Punto2D, b: Punto2D) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    longitud = math.hypot(dx, dy)
    if longitud < 1e-12:
        return math.hypot(px - ax, py - ay)
    return abs((px - ax) * dy - (py - ay) * dx) / longitud
