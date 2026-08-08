"""Lienzo de dibujo del plano.

El pintado se apoya en la transformación del propio `QPainter`: la geometría se
entrega en coordenadas de dibujo y es Qt quien la lleva a pantalla. Esto evita
recorrer millones de puntos en Python en cada repintado, que es lo que hace
inservible un visor con planos grandes.

Dos detalles gobiernan el resultado en pantalla:

- **El eje Y va invertido.** En CAD crece hacia arriba y en Qt hacia abajo, de
  modo que la transformación lo refleja y los textos han de compensarlo para no
  salir en espejo.
- **Los trazos son cosméticos.** Su grosor se mide en píxeles y no en unidades
  de dibujo, así que una línea sigue viéndose igual de fina al alejarse. De lo
  contrario, un plano en metros mostraría trazos invisibles y uno en milímetros
  manchas negras.
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

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from ..core.geometria import Extension
from ..core.medicion import Medicion
from ..core.modelo import Documento, Entidad, Polilinea, Punto, Relleno, Texto

#: Fondo del lienzo. Se mantiene muy oscuro y neutro para no falsear los
#: colores de capa, que en los planos de excavación codifican información.
COLOR_FONDO = QColor(24, 26, 30)

#: Ampliación y reducción por cada muesca de la rueda.
FACTOR_RUEDA = 1.18

#: Márgenes de zoom, para no perder el dibujo de vista por accidente.
ESCALA_MINIMA = 1e-6
ESCALA_MAXIMA = 1e7

#: Margen que se deja alrededor del dibujo al encuadrarlo.
MARGEN_ENCUADRE = 0.05

#: Tamaño en píxeles de la marca con que se dibujan las entidades POINT.
RADIO_PUNTO_PX = 2.5

#: Altura en píxeles de la fuente de referencia. El texto se escala desde ella,
#: porque Qt no admite tamaños de fuente en unidades de dibujo.
ALTURA_FUENTE_BASE = 100.0

#: Por debajo de este tamaño en pantalla el texto es ilegible y solo consume
#: tiempo de pintado, así que se omite.
ALTURA_MINIMA_TEXTO_PX = 4.0

#: Color de la cinta de medir. Se elige un tono que no aparece en la paleta ACI
#: de AutoCAD, para que no se confunda con geometría del plano.
COLOR_MEDICION = QColor(255, 140, 0)

#: Radio en píxeles de los vértices marcados al medir.
RADIO_VERTICE_PX = 4.0


class VistaPlano(QWidget):
    """Muestra un `Documento` con desplazamiento y zoom."""

    #: Coordenadas del dibujo bajo el cursor, para la barra de estado.
    cursor_movido = Signal(float, float)
    #: Escala actual en píxeles por unidad de dibujo.
    escala_cambiada = Signal(float)
    #: Resumen de la medición en curso, para la barra de estado.
    medicion_cambiada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._documento: Documento | None = None
        self._escala = 1.0
        self._centro = QPointF(0.0, 0.0)  # en coordenadas de dibujo
        self._arrastrando = False
        self._ultimo_raton = QPointF()

        self._medicion = Medicion()
        self._midiendo = False
        #: Posición del cursor en coordenadas del plano, para dibujar el tramo
        #: en curso antes de fijar el punto.
        self._cursor: QPointF | None = None

        #: Geometría preparada para Qt, agrupada por capa. Construirla una vez
        #: y no en cada repintado es lo que sostiene el rendimiento.
        self._poligonos: dict[str, list[tuple[QPolygonF, Entidad]]] = {}

    # -- carga -----------------------------------------------------------

    def cargar(self, documento: Documento | None) -> None:
        self._documento = documento
        self._medicion = Medicion(
            unidad=documento.unidad if documento else self._medicion.unidad
        )
        self._preparar_geometria()
        self.encuadrar_todo()

    # -- medición --------------------------------------------------------

    def activar_medicion(self, activa: bool) -> None:
        """Entra o sale del modo de medición."""
        self._midiendo = activa
        if not activa:
            self._medicion.limpiar()
        self.setCursor(
            Qt.CursorShape.CrossCursor if activa else Qt.CursorShape.ArrowCursor
        )
        self._emitir_medicion()
        self.update()

    @property
    def midiendo(self) -> bool:
        return self._midiendo

    def limpiar_medicion(self) -> None:
        self._medicion.limpiar()
        self._emitir_medicion()
        self.update()

    def deshacer_punto(self) -> None:
        self._medicion.deshacer()
        self._emitir_medicion()
        self.update()

    def _emitir_medicion(self) -> None:
        self.medicion_cambiada.emit(
            self._medicion.resumen() if self._midiendo else ""
        )

    @property
    def documento(self) -> Documento | None:
        return self._documento

    def _preparar_geometria(self) -> None:
        """Traduce las primitivas del modelo a polígonos de Qt."""
        self._poligonos.clear()
        if self._documento is None:
            return

        for entidad in self._documento.entidades:
            poligonos = _poligonos_de(entidad)
            if not poligonos:
                continue
            destino = self._poligonos.setdefault(entidad.capa, [])
            for poligono in poligonos:
                destino.append((poligono, entidad))

    # -- encuadre --------------------------------------------------------

    def encuadrar_todo(self) -> None:
        """Ajusta el zoom para que quepa todo el dibujo."""
        if self._documento is None:
            self._escala, self._centro = 1.0, QPointF(0.0, 0.0)
            self.update()
            return
        self._encuadrar(self._documento.extension())

    def encuadrar_capas(self, capas: list[str]) -> None:
        """Encuadra solo las capas indicadas."""
        if self._documento is None or not capas:
            return
        entidades = self._documento.entidades_de(capas)
        if not entidades:
            return
        self._encuadrar(Extension.union(e.extension() for e in entidades))

    def _encuadrar(self, extension: Extension) -> None:
        if extension.vacia or self.width() <= 0 or self.height() <= 0:
            return

        ancho = max(extension.ancho, 1e-9)
        alto = max(extension.alto, 1e-9)
        escala = min(self.width() / ancho, self.height() / alto) * (1 - 2 * MARGEN_ENCUADRE)

        self._escala = _acotar(escala, ESCALA_MINIMA, ESCALA_MAXIMA)
        cx, cy = extension.centro
        self._centro = QPointF(cx, cy)
        self.escala_cambiada.emit(self._escala)
        self.update()

    # -- transformación --------------------------------------------------

    def _a_pantalla(self, x: float, y: float) -> QPointF:
        return QPointF(
            (x - self._centro.x()) * self._escala + self.width() / 2,
            self.height() / 2 - (y - self._centro.y()) * self._escala,
        )

    def _a_dibujo(self, px: float, py: float) -> QPointF:
        return QPointF(
            (px - self.width() / 2) / self._escala + self._centro.x(),
            self._centro.y() - (py - self.height() / 2) / self._escala,
        )

    def _ventana_visible(self) -> Extension:
        """Rectángulo del dibujo que cabe en pantalla, para el descarte."""
        esquina1 = self._a_dibujo(0, 0)
        esquina2 = self._a_dibujo(self.width(), self.height())
        return Extension(
            min(esquina1.x(), esquina2.x()),
            min(esquina1.y(), esquina2.y()),
            max(esquina1.x(), esquina2.x()),
            max(esquina1.y(), esquina2.y()),
        )

    # -- pintado ---------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), COLOR_FONDO)

        if self._documento is None or not self._poligonos:
            painter.end()
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Se traslada y escala el painter, de modo que a partir de aquí se
        # dibuja directamente en coordenadas del plano.
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(self._escala, -self._escala)
        painter.translate(-self._centro.x(), -self._centro.y())

        visible = self._ventana_visible()
        pluma = QPen()
        pluma.setCosmetic(True)  # grosor en píxeles, independiente del zoom
        pluma.setWidthF(1.0)
        pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        for nombre, elementos in self._poligonos.items():
            capa = self._documento.capas.get(nombre)
            if capa is not None and not capa.dibujable:
                continue

            color_capa = QColor(*(capa.color if capa else (255, 255, 255)))
            for poligono, entidad in elementos:
                if not entidad.extension().intersecta(visible):
                    continue

                color = QColor(*entidad.color) if entidad.color else color_capa
                pluma.setColor(color)
                painter.setPen(pluma)

                if isinstance(entidad, Relleno):
                    self._pintar_relleno(painter, poligono, color, entidad)
                elif isinstance(entidad, Texto):
                    self._pintar_texto(painter, entidad, color)
                elif isinstance(entidad, Punto):
                    self._pintar_punto(painter, entidad, color)
                elif isinstance(entidad, Polilinea):
                    if entidad.cerrada:
                        painter.drawPolygon(poligono)
                    else:
                        painter.drawPolyline(poligono)

        if self._midiendo:
            self._pintar_medicion(painter)

        painter.end()

    def _pintar_medicion(self, painter: QPainter) -> None:
        """Dibuja la cinta de medir por encima del plano."""
        puntos = self._medicion.puntos
        if not puntos:
            return

        pluma = QPen(COLOR_MEDICION)
        pluma.setCosmetic(True)
        pluma.setWidthF(1.6)
        painter.setPen(pluma)

        cadena = QPolygonF([QPointF(x, y) for x, y in puntos])
        if self._cursor is not None:
            cadena.append(self._cursor)
        painter.drawPolyline(cadena)

        # Con tres o más vértices se insinúa el cierre, que es lo que define la
        # superficie que se está midiendo.
        if len(puntos) >= 3:
            pluma_cierre = QPen(COLOR_MEDICION)
            pluma_cierre.setCosmetic(True)
            pluma_cierre.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pluma_cierre)
            painter.drawLine(
                QPointF(*puntos[-1]) if self._cursor is None else self._cursor,
                QPointF(*puntos[0]),
            )
            painter.setPen(pluma)

        radio = RADIO_VERTICE_PX / self._escala
        painter.setBrush(QBrush(COLOR_MEDICION))
        for x, y in puntos:
            painter.drawEllipse(QPointF(x, y), radio, radio)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _pintar_relleno(
        self, painter: QPainter, poligono: QPolygonF, color: QColor, entidad: Relleno
    ) -> None:
        if entidad.solido:
            # Se rebaja la opacidad para que el relleno no tape la geometría
            # que queda debajo, algo habitual al marcar unidades excavadas.
            relleno = QColor(color)
            relleno.setAlpha(90)
            painter.setBrush(QBrush(relleno))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(poligono)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _pintar_texto(self, painter: QPainter, entidad: Texto, color: QColor) -> None:
        altura_px = entidad.altura * self._escala
        if altura_px < ALTURA_MINIMA_TEXTO_PX:
            return

        painter.save()
        painter.translate(entidad.posicion[0], entidad.posicion[1])
        # Se deshace la inversión del eje Y para que el texto no salga en
        # espejo, y se aplica la rotación propia de la entidad.
        painter.scale(1.0, -1.0)
        if entidad.rotacion:
            painter.rotate(-entidad.rotacion)

        factor = entidad.altura / ALTURA_FUENTE_BASE
        painter.scale(factor, factor)

        fuente = QFont()
        fuente.setPixelSize(int(ALTURA_FUENTE_BASE))
        painter.setFont(fuente)
        painter.setPen(QPen(color))

        # Un MTEXT es a menudo un párrafo; sus líneas se escriben una debajo de
        # otra, no concatenadas.
        salto = ALTURA_FUENTE_BASE * entidad.interlineado
        for indice, linea in enumerate(entidad.lineas):
            painter.drawText(QPointF(0.0, indice * salto), linea)
        painter.restore()

    def _pintar_punto(self, painter: QPainter, entidad: Punto, color: QColor) -> None:
        # El radio se fija en píxeles: un punto debe verse igual a cualquier zoom.
        radio = RADIO_PUNTO_PX / self._escala
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(*entidad.posicion), radio, radio)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    # -- interacción -----------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - API de Qt
        """Zoom centrado en el cursor, que es lo que se espera al examinar detalle."""
        muescas = event.angleDelta().y() / 120.0
        if not muescas:
            return

        antes = self._a_dibujo(event.position().x(), event.position().y())
        self._escala = _acotar(
            self._escala * (FACTOR_RUEDA**muescas), ESCALA_MINIMA, ESCALA_MAXIMA
        )
        despues = self._a_dibujo(event.position().x(), event.position().y())

        # Se corrige el centro para que el punto bajo el cursor no se mueva.
        self._centro += antes - despues
        self.escala_cambiada.emit(self._escala)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API de Qt
        if self._midiendo and event.button() == Qt.MouseButton.LeftButton:
            posicion = self._a_dibujo(event.position().x(), event.position().y())
            self._medicion.anadir((posicion.x(), posicion.y()))
            self._emitir_medicion()
            self.update()
            return

        if self._midiendo and event.button() == Qt.MouseButton.RightButton:
            # El botón derecho retira el último punto: es lo que se espera al
            # marcar un vértice de más sobre un contorno irregular.
            self.deshacer_punto()
            return

        # Midiendo, el desplazamiento queda en el botón central para no
        # interferir con el marcado de puntos.
        botones = (
            (Qt.MouseButton.MiddleButton,)
            if self._midiendo
            else (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)
        )
        if event.button() in botones:
            self._arrastrando = True
            self._ultimo_raton = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API de Qt
        posicion = event.position()
        if self._arrastrando:
            delta = posicion - self._ultimo_raton
            self._centro -= QPointF(
                delta.x() / self._escala, -delta.y() / self._escala
            )
            self._ultimo_raton = posicion
            self.update()

        en_dibujo = self._a_dibujo(posicion.x(), posicion.y())
        self.cursor_movido.emit(en_dibujo.x(), en_dibujo.y())

        if self._midiendo:
            self._cursor = en_dibujo
            if self._medicion.activa:
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API de Qt
        self._arrastrando = False
        self.setCursor(
            Qt.CursorShape.CrossCursor if self._midiendo else Qt.CursorShape.ArrowCursor
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API de Qt
        # Midiendo, el doble clic marcaría un punto por partida doble y además
        # reencuadraría, que no es lo que se busca.
        if not self._midiendo:
            self.encuadrar_todo()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._midiendo:
            if event.key() == Qt.Key.Key_Escape:
                self.limpiar_medicion()
                return
            if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                self.deshacer_punto()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        # Con el widget aún sin dimensionar, el primer encuadre no puede
        # calcularse; se rehace en cuanto hay tamaño real.
        if event.oldSize().width() <= 0 and self._documento is not None:
            self.encuadrar_todo()


def _poligonos_de(entidad: Entidad) -> list[QPolygonF]:
    """Convierte una primitiva del modelo en polígonos de Qt."""
    if isinstance(entidad, Polilinea):
        puntos = list(entidad.puntos)
        if entidad.cerrada and puntos:
            puntos.append(puntos[0])
        return [QPolygonF([QPointF(x, y) for x, y in puntos])]

    if isinstance(entidad, Relleno):
        return [QPolygonF([QPointF(x, y) for x, y in c]) for c in entidad.contornos]

    # Puntos y textos no necesitan polígono, pero deben figurar en la lista de
    # pintado; se les asocia uno vacío como marcador de posición.
    if isinstance(entidad, (Punto, Texto)):
        return [QPolygonF()]

    return []


def _acotar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(valor, maximo))
