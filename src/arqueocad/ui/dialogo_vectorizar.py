"""Diálogo de vectorización de imágenes.

Dos ideas gobiernan esta ventana.

La primera es que **el umbral hay que verlo**. Ningún número dice de antemano
cuánto trazo se conserva y cuánto ruido entra: hay que mirar la imagen
binarizada. Por eso la previsualización se actualiza al mover el control, y
muestra exactamente lo que se va a seguir después.

La segunda es que **sin calibrar no hay medidas**. Una imagen no tiene escala,
de modo que el resultado saldría en píxeles. Marcando dos puntos de distancia
conocida —lo natural es la escala gráfica del propio plano— el dibujo pasa a
estar en metros y sirve para medir.
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

from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, QThread, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.idioma import t
from ..core.modelo import Documento
from ..core.unidades import Unidad
from ..core.unidades import nombre as nombre_unidad
from ..io.vectorizador import (
    EstrategiaCapas,
    OpcionesVectorizado,
    ResultadoVectorizado,
    calcular_escala,
    vectorizar,
)

#: Unidades que se ofrecen para la calibración.
UNIDADES = (Unidad.METROS, Unidad.CENTIMETROS, Unidad.MILIMETROS)

#: Lado máximo de la previsualización, en píxeles. Binarizar la imagen completa
#: en cada movimiento del control sería demasiado lento con una foto grande.
LADO_PREVIA = 900


class _Lienzo(QWidget):
    """Muestra la previsualización y recoge los puntos de calibración."""

    punto_marcado = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self._pixmap: QPixmap | None = None
        self._puntos: list[tuple[float, float]] = []
        self._calibrando = False

    def mostrar(self, imagen: QImage) -> None:
        self._pixmap = QPixmap.fromImage(imagen)
        self.update()

    def calibrar(self, activo: bool) -> None:
        self._calibrando = activo
        self._puntos.clear()
        self.setCursor(
            Qt.CursorShape.CrossCursor if activo else Qt.CursorShape.ArrowCursor
        )
        self.update()

    @property
    def puntos(self) -> list[tuple[float, float]]:
        return list(self._puntos)

    def _destino(self) -> QRect:
        """Rectángulo donde se pinta la imagen, conservando su proporción."""
        if self._pixmap is None:
            return QRect()
        escalado = self._pixmap.size().scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = (self.width() - escalado.width()) // 2
        y = (self.height() - escalado.height()) // 2
        return QRect(QPoint(x, y), escalado)

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        pintor = QPainter(self)
        pintor.fillRect(self.rect(), QColor(40, 42, 46))

        if self._pixmap is None:
            pintor.setPen(QColor(160, 160, 160))
            pintor.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, t("Sin imagen")
            )
            pintor.end()
            return

        destino = self._destino()
        pintor.drawPixmap(destino, self._pixmap)

        if self._puntos:
            pluma = QPen(QColor(255, 140, 0))
            pluma.setWidth(2)
            pintor.setPen(pluma)
            en_pantalla = [self._a_pantalla(p, destino) for p in self._puntos]
            for punto in en_pantalla:
                pintor.drawLine(punto.x() - 8, punto.y(), punto.x() + 8, punto.y())
                pintor.drawLine(punto.x(), punto.y() - 8, punto.x(), punto.y() + 8)
            if len(en_pantalla) == 2:
                pintor.drawLine(en_pantalla[0], en_pantalla[1])

        pintor.end()

    def _a_pantalla(self, punto, destino: QRect) -> QPoint:
        if self._pixmap is None or self._pixmap.width() == 0:
            return QPoint()
        factor = destino.width() / self._pixmap.width()
        return QPoint(
            int(destino.x() + punto[0] * factor),
            int(destino.y() + punto[1] * factor),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API de Qt
        if not self._calibrando or self._pixmap is None:
            return

        destino = self._destino()
        if not destino.contains(event.position().toPoint()):
            return

        factor = self._pixmap.width() / max(destino.width(), 1)
        x = (event.position().x() - destino.x()) * factor
        y = (event.position().y() - destino.y()) * factor

        # Solo interesan dos puntos: el tercero reinicia la medida.
        if len(self._puntos) >= 2:
            self._puntos.clear()
        self._puntos.append((x, y))
        self.punto_marcado.emit(x, y)
        self.update()


class _Trabajador(QObject):
    terminado = Signal(object)
    fallido = Signal(str)

    def __init__(self, ruta: Path, opciones: OpcionesVectorizado) -> None:
        super().__init__()
        self._ruta = ruta
        self._opciones = opciones

    @Slot()
    def ejecutar(self) -> None:
        try:
            resultado = vectorizar(self._ruta, self._opciones)
        except Exception as exc:  # noqa: BLE001
            self.fallido.emit(str(exc))
        else:
            self.terminado.emit(resultado)


class DialogoVectorizar(QDialog):
    """Convierte una imagen en geometría, con previsualización y calibración."""

    #: Documento resultante, una vez aceptado el diálogo.
    documento: Documento | None = None

    def __init__(self, ruta: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("Vectorizar imagen"))
        self.resize(1100, 720)

        self._ruta = Path(ruta)
        self._hilo: QThread | None = None
        self._trabajador: _Trabajador | None = None

        self._original = self._cargar()
        self._reducida = self._reducir(self._original)

        principal = QHBoxLayout(self)
        self._lienzo = _Lienzo(self)
        principal.addWidget(self._lienzo, stretch=3)

        panel = QVBoxLayout()
        panel.addWidget(self._grupo_trazo())
        panel.addWidget(self._grupo_capas())
        panel.addWidget(self._grupo_escala())
        panel.addStretch(1)

        self._progreso = QProgressBar()
        self._progreso.setRange(0, 0)
        self._progreso.hide()
        panel.addWidget(self._progreso)

        self._estado = QLabel("")
        self._estado.setWordWrap(True)
        panel.addWidget(self._estado)

        botones = QDialogButtonBox()
        self._boton_aceptar = botones.addButton(
            t("Vectorizar"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        cancelar = botones.addButton(
            t("Cancelar"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self._boton_aceptar.clicked.connect(self._vectorizar)
        cancelar.clicked.connect(self.reject)
        panel.addWidget(botones)

        principal.addLayout(panel, stretch=2)

        self._lienzo.punto_marcado.connect(self._al_marcar)
        self._actualizar_previa()

    # -- carga -----------------------------------------------------------

    def _cargar(self) -> np.ndarray:
        import cv2

        datos = np.fromfile(str(self._ruta), dtype=np.uint8)
        imagen = cv2.imdecode(datos, cv2.IMREAD_COLOR)
        if imagen is None:
            raise ValueError(f"No se puede leer la imagen «{self._ruta.name}».")
        return imagen

    def _reducir(self, imagen: np.ndarray) -> np.ndarray:
        """Versión pequeña para previsualizar sin penalizar cada ajuste."""
        import cv2

        alto, ancho = imagen.shape[:2]
        mayor = max(alto, ancho)
        if mayor <= LADO_PREVIA:
            return imagen
        factor = LADO_PREVIA / mayor
        return cv2.resize(imagen, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)

    # -- controles -------------------------------------------------------

    def _grupo_trazo(self) -> QGroupBox:
        grupo = QGroupBox(t("Detección del trazo"))
        disposicion = QFormLayout(grupo)

        self._auto = QCheckBox(t("Umbral automático"))
        self._auto.setChecked(True)
        self._auto.toggled.connect(self._actualizar_previa)
        disposicion.addRow(self._auto)

        self._umbral = QSlider(Qt.Orientation.Horizontal)
        self._umbral.setRange(1, 254)
        self._umbral.setValue(128)
        self._umbral.valueChanged.connect(self._actualizar_previa)
        disposicion.addRow(t("Umbral:"), self._umbral)

        self._iluminacion = QCheckBox(t("Corregir la iluminación desigual"))
        self._iluminacion.setChecked(True)
        self._iluminacion.setToolTip(
            t(
                "Imprescindible en fotografías: sin esto, un umbral único "
                "ennegrece la zona más oscura y blanquea la contraria."
            )
        )
        self._iluminacion.toggled.connect(self._actualizar_previa)
        disposicion.addRow(self._iluminacion)

        self._invertir = QCheckBox(t("El dibujo es claro sobre fondo oscuro"))
        self._invertir.toggled.connect(self._actualizar_previa)
        disposicion.addRow(self._invertir)

        self._area = QSpinBox()
        self._area.setRange(0, 500)
        self._area.setValue(12)
        self._area.setSuffix(" px")
        self._area.valueChanged.connect(self._actualizar_previa)
        disposicion.addRow(t("Manchas menores que:"), self._area)

        self._tolerancia = QDoubleSpinBox()
        self._tolerancia.setRange(0.1, 10.0)
        self._tolerancia.setSingleStep(0.1)
        self._tolerancia.setValue(1.2)
        self._tolerancia.setSuffix(" px")
        self._tolerancia.setToolTip(
            t("Subirla da archivos más ligeros a costa de redondear las esquinas.")
        )
        disposicion.addRow(t("Simplificación:"), self._tolerancia)

        return grupo

    def _grupo_capas(self) -> QGroupBox:
        grupo = QGroupBox(t("Capas"))
        disposicion = QVBoxLayout(grupo)

        self._estrategia = QComboBox()
        self._estrategia.addItem(t("Una sola capa"), EstrategiaCapas.UNICA)
        self._estrategia.addItem(t("Por grosor del trazo"), EstrategiaCapas.GROSOR)
        self._estrategia.addItem(t("Por color del trazo"), EstrategiaCapas.COLOR)
        disposicion.addWidget(self._estrategia)

        aviso = QLabel(
            t(
                "La separación es gráfica, no de significado: no puede distinguir "
                "un muro de una cota si están dibujados igual."
            )
        )
        aviso.setWordWrap(True)
        disposicion.addWidget(aviso)

        return grupo

    def _grupo_escala(self) -> QGroupBox:
        grupo = QGroupBox(t("Escala"))
        disposicion = QFormLayout(grupo)

        self._calibrar = QPushButton(t("Marcar dos puntos…"))
        self._calibrar.setCheckable(True)
        self._calibrar.setToolTip(
            t("Lo natural es marcar los extremos de la escala gráfica del plano.")
        )
        self._calibrar.toggled.connect(self._lienzo_calibrar)
        disposicion.addRow(self._calibrar)

        self._distancia = QDoubleSpinBox()
        self._distancia.setRange(0.001, 1_000_000.0)
        self._distancia.setDecimals(3)
        self._distancia.setValue(10.0)
        disposicion.addRow(t("Distancia real:"), self._distancia)

        self._unidad = QComboBox()
        for unidad in UNIDADES:
            self._unidad.addItem(t(nombre_unidad(unidad)), unidad)
        disposicion.addRow(t("Unidad:"), self._unidad)

        self._aviso_escala = QLabel(
            t("Sin calibrar, el resultado sale en píxeles y no sirve para medir.")
        )
        self._aviso_escala.setWordWrap(True)
        disposicion.addRow(self._aviso_escala)

        return grupo

    # -- previsualización ------------------------------------------------

    def _opciones(self, para_previa: bool = False) -> OpcionesVectorizado:
        escala, unidad = self._escala_calibrada()
        return OpcionesVectorizado(
            estrategia=self._estrategia.currentData(),
            umbral=None if self._auto.isChecked() else self._umbral.value(),
            corregir_iluminacion=self._iluminacion.isChecked(),
            trazo_oscuro=not self._invertir.isChecked(),
            area_minima=self._area.value(),
            tolerancia=self._tolerancia.value(),
            escala=escala,
            unidad=unidad,
        )

    def _escala_calibrada(self) -> tuple[float, Unidad]:
        puntos = self._lienzo.puntos
        if len(puntos) != 2:
            return 1.0, Unidad.SIN_DEFINIR

        # Los puntos se marcan sobre la previsualización reducida; hay que
        # llevarlos a las coordenadas de la imagen original.
        factor = self._original.shape[1] / max(self._reducida.shape[1], 1)
        p1 = (puntos[0][0] * factor, puntos[0][1] * factor)
        p2 = (puntos[1][0] * factor, puntos[1][1] * factor)

        try:
            escala = calcular_escala(p1, p2, self._distancia.value())
        except Exception:  # noqa: BLE001
            return 1.0, Unidad.SIN_DEFINIR
        return escala, self._unidad.currentData()

    def _actualizar_previa(self) -> None:
        """Muestra la imagen binarizada con los ajustes actuales."""
        self._umbral.setEnabled(not self._auto.isChecked())

        from ..core.modelo import Documento as _Doc
        from ..core.modelo import FormatoOrigen
        from ..io.vectorizador import _binarizar

        provisional = _Doc(ruta="", formato=FormatoOrigen.RASTER)
        binaria = _binarizar(self._reducida, self._opciones(para_previa=True), provisional)

        # El trazo se muestra oscuro sobre claro, como el dibujo original.
        visible = 255 - binaria
        alto, ancho = visible.shape
        imagen = QImage(visible.data, ancho, alto, ancho, QImage.Format.Format_Grayscale8)
        self._lienzo.mostrar(imagen.copy())

        cubierto = float((binaria > 0).mean()) * 100
        self._estado.setText(
            t("Trazo detectado: {pct} % de la imagen").format(pct=f"{cubierto:.1f}")
        )

    def _lienzo_calibrar(self, activo: bool) -> None:
        self._lienzo.calibrar(activo)
        if activo:
            self._estado.setText(
                t("Marque dos puntos de distancia conocida sobre la imagen.")
            )

    def _al_marcar(self, x: float, y: float) -> None:
        puntos = self._lienzo.puntos
        if len(puntos) < 2:
            self._estado.setText(t("Marque el segundo punto."))
            return

        escala, unidad = self._escala_calibrada()
        if unidad is Unidad.SIN_DEFINIR:
            return
        self._aviso_escala.setText(
            t("Calibrado: {v} unidades de dibujo por píxel.").format(v=f"{escala:.6g}")
        )
        self._calibrar.setChecked(False)

    # -- ejecución -------------------------------------------------------

    def _vectorizar(self) -> None:
        self._progreso.show()
        self._boton_aceptar.setEnabled(False)
        self._estado.setText(t("Vectorizando…"))

        self._hilo = QThread(self)
        self._trabajador = _Trabajador(self._ruta, self._opciones())
        self._trabajador.moveToThread(self._hilo)
        self._hilo.started.connect(self._trabajador.ejecutar)
        self._trabajador.terminado.connect(self._al_terminar)
        self._trabajador.fallido.connect(self._al_fallar)
        self._hilo.start()

    @Slot(object)
    def _al_terminar(self, resultado: ResultadoVectorizado) -> None:
        self._detener()
        self.documento = resultado.documento
        self.accept()

    @Slot(str)
    def _al_fallar(self, mensaje: str) -> None:
        self._detener()
        self._estado.setText(f"✕  {mensaje}")

    def _detener(self) -> None:
        self._progreso.hide()
        self._boton_aceptar.setEnabled(True)
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait()
            self._hilo = None
        self._trabajador = None

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._detener()
        super().closeEvent(event)
