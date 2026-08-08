"""Ventana principal de ArqueoCAD."""

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

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QWidget,
)

from .. import __version__
from ..core.modelo import Documento
from ..core.unidades import nombre as nombre_unidad
from ..core.unidades import simbolo
from ..io import (
    ConversionDWGError,
    FormatoNoAdmitido,
    LecturaDXFError,
    LecturaSVGError,
    SinConversor,
    leer,
)
from .dialogo_exportar import DialogoExportar
from .dialogo_lotes import DialogoLotes
from .panel_capas import PanelCapas
from .vista_plano import VistaPlano

#: Extensiones que la aplicación acepta arrastrar o abrir.
FILTRO_ARCHIVOS = (
    "Planos admitidos (*.dxf *.dwg *.svg);;"
    "AutoCAD DXF (*.dxf);;"
    "AutoCAD DWG (*.dwg);;"
    "SVG (*.svg);;"
    "Todos los archivos (*)"
)


def _carpeta_licencias() -> Path | None:
    """Localiza la carpeta de licencias, esté la aplicación empaquetada o no."""
    candidatas = []
    empaquetado = getattr(sys, "_MEIPASS", None)
    if empaquetado:
        # En el ejecutable, la carpeta se instala junto al programa, no dentro
        # del paquete temporal: así el usuario puede llegar a ella.
        candidatas.append(Path(sys.executable).parent / "licencias")
        candidatas.append(Path(empaquetado) / "licencias")
    candidatas.append(Path(__file__).resolve().parents[3] / "licencias")

    for carpeta in candidatas:
        if carpeta.is_dir():
            return carpeta
    return None


class _Cargador(QObject):
    """Lee un archivo fuera del hilo de la interfaz.

    Un plano de excavación puede pasar del centenar de miles de entidades; leerlo
    en el hilo principal congelaría la ventana durante segundos y daría la
    impresión de que la aplicación ha dejado de responder.
    """

    terminado = Signal(object)
    #: Mensaje y si se trata de la falta de un conversor de DWG, que no es un
    #: error del archivo sino algo que el usuario puede resolver instalando un
    #: programa.
    fallido = Signal(str, bool)

    def __init__(self, ruta: Path) -> None:
        super().__init__()
        self._ruta = ruta

    @Slot()
    def ejecutar(self) -> None:
        try:
            documento = leer(self._ruta)
        except SinConversor as exc:
            self.fallido.emit(str(exc), True)
        except (
            LecturaDXFError,
            LecturaSVGError,
            FormatoNoAdmitido,
            ConversionDWGError,
            FileNotFoundError,
        ) as exc:
            self.fallido.emit(str(exc), False)
        except Exception as exc:  # noqa: BLE001 - la ventana debe sobrevivir
            self.fallido.emit(f"Error inesperado al leer el archivo: {exc}", False)
        else:
            self.terminado.emit(documento)


class VentanaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ArqueoCAD")
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self._documento: Documento | None = None
        self._hilo: QThread | None = None
        self._cargador: _Cargador | None = None

        self._vista = VistaPlano(self)
        self.setCentralWidget(self._vista)

        self._panel = PanelCapas(self)
        muelle = QDockWidget("Capas", self)
        muelle.setWidget(self._panel)
        muelle.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, muelle)
        self._muelle_capas = muelle
        # Los nombres de capa de excavación son largos —«PERÍMETRO_EXCAVADO_2024»,
        # «COTA_PLOTEO_2024»— y con el ancho que Qt asigna por defecto quedan
        # truncados justo en la parte que los distingue.
        self.resizeDocks([muelle], [380], Qt.Orientation.Horizontal)

        self._construir_acciones()
        self._construir_barra_estado()

        self._panel.visibilidad_cambiada.connect(self._vista.update)
        self._panel.encuadre_pedido.connect(self._vista.encuadrar_capas)
        self._vista.cursor_movido.connect(self._mostrar_coordenadas)
        self._vista.escala_cambiada.connect(self._mostrar_escala)
        self._vista.medicion_cambiada.connect(self._mostrar_medicion)

    # -- construcción ----------------------------------------------------

    def _construir_acciones(self) -> None:
        barra = self.addToolBar("Principal")
        barra.setMovable(False)

        menu_archivo = self.menuBar().addMenu("&Archivo")
        menu_ver = self.menuBar().addMenu("&Ver")
        menu_ayuda = self.menuBar().addMenu("A&yuda")

        abrir = QAction("&Abrir plano…", self)
        abrir.setShortcut(QKeySequence.StandardKey.Open)
        abrir.triggered.connect(self.abrir_dialogo)
        menu_archivo.addAction(abrir)
        barra.addAction(abrir)

        menu_archivo.addSeparator()
        salir = QAction("&Salir", self)
        salir.setShortcut(QKeySequence.StandardKey.Quit)
        salir.triggered.connect(self.close)
        menu_archivo.addAction(salir)

        self._accion_separar = QAction("&Separar por capas…", self)
        self._accion_separar.setShortcut("Ctrl+E")
        self._accion_separar.setEnabled(False)
        self._accion_separar.triggered.connect(self._separar)
        menu_archivo.insertAction(salir, self._accion_separar)
        menu_archivo.insertSeparator(salir)
        barra.addAction(self._accion_separar)

        barra.addSeparator()

        encuadrar = QAction("Encuadrar &todo", self)
        encuadrar.setShortcut("Ctrl+0")
        encuadrar.triggered.connect(self._vista.encuadrar_todo)
        menu_ver.addAction(encuadrar)
        barra.addAction(encuadrar)

        encuadrar_sel = QAction("Encuadrar la &selección", self)
        encuadrar_sel.setShortcut("Ctrl+Shift+0")
        encuadrar_sel.triggered.connect(
            lambda: self._vista.encuadrar_capas(self._panel.capas_seleccionadas())
        )
        menu_ver.addAction(encuadrar_sel)

        menu_ver.addSeparator()
        menu_ver.addAction(self._muelle_capas.toggleViewAction())

        barra.addSeparator()

        self._accion_medir = QAction("&Medir", self)
        self._accion_medir.setCheckable(True)
        self._accion_medir.setShortcut("M")
        self._accion_medir.setToolTip(
            "Marque puntos con el botón izquierdo. El derecho retira el último, "
            "Esc limpia la medición y el botón central desplaza el plano."
        )
        self._accion_medir.toggled.connect(self._alternar_medicion)
        menu_ver.addSeparator()
        menu_ver.addAction(self._accion_medir)
        barra.addAction(self._accion_medir)

        self._accion_lotes = QAction("Separar por &lotes…", self)
        self._accion_lotes.setShortcut("Ctrl+L")
        self._accion_lotes.setToolTip(
            "Separa varios planos de una campaña con las mismas opciones."
        )
        self._accion_lotes.triggered.connect(self._separar_lotes)
        menu_archivo.insertAction(self._accion_separar, self._accion_lotes)
        barra.addAction(self._accion_lotes)

        self._accion_avisos = QAction("&Avisos del archivo…", self)
        self._accion_avisos.triggered.connect(self._mostrar_avisos)
        self._accion_avisos.setEnabled(False)
        menu_ayuda.addAction(self._accion_avisos)
        barra.addAction(self._accion_avisos)

        conversores = QAction("&Conversores de DWG…", self)
        conversores.triggered.connect(self._mostrar_conversores)
        menu_ayuda.addAction(conversores)

        acerca = QAction("Acerca de Arqueo&CAD", self)
        acerca.triggered.connect(self._mostrar_acerca_de)
        menu_ayuda.addAction(acerca)

    def _construir_barra_estado(self) -> None:
        self._etiqueta_archivo = QLabel("Ningún plano abierto")
        self._etiqueta_medicion = QLabel("")
        self._etiqueta_medicion.hide()
        self._etiqueta_coordenadas = QLabel("")
        self._etiqueta_escala = QLabel("")
        self._progreso = QProgressBar()
        self._progreso.setRange(0, 0)  # indeterminado
        self._progreso.setMaximumWidth(140)
        self._progreso.hide()

        barra = self.statusBar()
        barra.addWidget(self._etiqueta_archivo, stretch=1)
        # Permanente: los mensajes temporales ocultan los widgets normales, y la
        # medición en curso no debe desaparecer porque salte un aviso.
        barra.addPermanentWidget(self._etiqueta_medicion)
        barra.addPermanentWidget(self._progreso)
        barra.addPermanentWidget(self._etiqueta_coordenadas)
        barra.addPermanentWidget(self._etiqueta_escala)

    # -- apertura --------------------------------------------------------

    def abrir_dialogo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir plano", "", FILTRO_ARCHIVOS
        )
        if ruta:
            self.abrir(Path(ruta))

    def abrir(self, ruta: Path) -> None:
        self._etiqueta_archivo.setText(f"Leyendo {ruta.name}…")
        self._progreso.show()
        self.setEnabled(False)

        self._hilo = QThread(self)
        self._cargador = _Cargador(ruta)
        self._cargador.moveToThread(self._hilo)
        self._hilo.started.connect(self._cargador.ejecutar)
        self._cargador.terminado.connect(self._al_cargar)
        self._cargador.fallido.connect(self._al_fallar)
        self._hilo.start()

    @Slot(object)
    def _al_cargar(self, documento: Documento) -> None:
        self._detener_hilo()
        self._documento = documento

        self._vista.cargar(documento)
        self._panel.cargar(documento)

        ruta = Path(documento.ruta)
        self.setWindowTitle(f"{ruta.name} — ArqueoCAD")
        self._etiqueta_archivo.setText(
            f"{ruta.name} · {len(documento.entidades):,} entidades · "
            f"{len(documento.capas)} capas · unidad: {nombre_unidad(documento.unidad)}".replace(",", ".")
        )

        self._accion_separar.setEnabled(True)

        graves = [a for a in documento.avisos if a.nivel in ("aviso", "error")]
        self._accion_avisos.setEnabled(bool(documento.avisos))
        self._accion_avisos.setText(
            f"&Avisos del archivo ({len(documento.avisos)})…"
            if documento.avisos
            else "&Avisos del archivo…"
        )
        if graves:
            self.statusBar().showMessage(
                f"El archivo se ha abierto con {len(graves)} avisos. "
                "Consúltalos en Ayuda › Avisos del archivo.",
                8000,
            )

    @Slot(str, bool)
    def _al_fallar(self, mensaje: str, falta_conversor: bool) -> None:
        self._detener_hilo()
        self._etiqueta_archivo.setText("Ningún plano abierto")

        if not falta_conversor:
            QMessageBox.critical(self, "No se ha podido abrir el plano", mensaje)
            return

        # Falta un programa, no está roto el archivo: el tono y el icono deben
        # decirlo, y el enlace tiene que poder pulsarse.
        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Hace falta un conversor de DWG")
        cuadro.setIcon(QMessageBox.Icon.Information)
        cuadro.setTextFormat(Qt.TextFormat.RichText)
        cuadro.setText(
            "<p>Para abrir archivos DWG hace falta un conversor externo, porque "
            "DWG es un formato propietario y cerrado.</p>"
            "<p>La opción recomendada es <b>ODA File Converter</b>, gratuito y con "
            "soporte completo:</p>"
            '<p><a href="https://www.opendesign.com/guestfiles/oda_file_converter">'
            "opendesign.com/guestfiles/oda_file_converter</a></p>"
            "<p>Una vez instalado, ArqueoCAD lo detecta solo.</p>"
            "<p>Como alternativa, el DWG puede exportarse a DXF desde el propio "
            "AutoCAD o desde BricsCAD.</p>"
        )
        cuadro.exec()

    def _detener_hilo(self) -> None:
        self._progreso.hide()
        self.setEnabled(True)
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait()
            self._hilo = None
        self._cargador = None

    # -- separación ------------------------------------------------------

    def _separar(self) -> None:
        if self._documento is None:
            return

        capas = self._panel.capas_seleccionadas()
        if not capas:
            QMessageBox.information(
                self,
                "Ninguna capa seleccionada",
                "Seleccione en el panel de capas las que quiere exportar.\n\n"
                "La casilla controla lo que se ve; la selección de filas, lo que se exporta.",
            )
            return

        DialogoExportar(self._documento, capas, self).exec()

    def _separar_lotes(self) -> None:
        DialogoLotes(self).exec()

    # -- medición --------------------------------------------------------

    def _alternar_medicion(self, activa: bool) -> None:
        # No se anuncia con un mensaje temporal: ocuparía el mismo hueco que el
        # resumen de la medición y se solaparían. El propio resumen guía
        # («marque el primer punto»), y las teclas están en la ayuda del botón.
        self._vista.activar_medicion(activa)
        self._vista.setFocus()

    @Slot(str)
    def _mostrar_medicion(self, resumen: str) -> None:
        self._etiqueta_medicion.setText(resumen)
        self._etiqueta_medicion.setVisible(bool(resumen))

    # -- información -----------------------------------------------------

    def _mostrar_avisos(self) -> None:
        if self._documento is None or not self._documento.avisos:
            return

        iconos = {"info": "·", "aviso": "▲", "error": "✕"}
        lineas = []
        for aviso in self._documento.avisos:
            lineas.append(f"{iconos.get(aviso.nivel, '·')}  {aviso.mensaje}")
            if aviso.detalle:
                lineas.append(f"     {aviso.detalle}")

        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Avisos del archivo")
        cuadro.setIcon(QMessageBox.Icon.Information)
        cuadro.setText(
            f"Se han registrado {len(self._documento.avisos)} incidencias al leer el plano."
        )
        cuadro.setDetailedText("\n".join(lineas))
        cuadro.exec()

    def _mostrar_conversores(self) -> None:
        """Informa de qué conversor de DWG se está usando y con qué alcance."""
        from ..io import detectar

        encontrados = detectar()

        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Conversores de DWG")
        cuadro.setIcon(QMessageBox.Icon.Information)
        cuadro.setTextFormat(Qt.TextFormat.RichText)

        if not encontrados:
            cuadro.setText(
                "<p>No se ha encontrado ningún conversor de DWG.</p>"
                "<p>ArqueoCAD abre DXF y SVG sin necesidad de nada más, pero para "
                "los DWG hace falta instalar "
                '<a href="https://www.opendesign.com/guestfiles/oda_file_converter">'
                "ODA File Converter</a>, que es gratuito.</p>"
            )
        else:
            filas = "".join(
                f"<li><b>{c.nombre}</b> — {'todas las versiones' if c.completo else 'soporte parcial de las versiones recientes'}"
                f"<br><small>{c.ruta}</small></li>"
                for c in encontrados
            )
            cuadro.setText(
                f"<p>Se usará <b>{encontrados[0].nombre}</b>.</p><ul>{filas}</ul>"
            )
        cuadro.exec()

    def _mostrar_acerca_de(self) -> None:
        # Se construye el cuadro a mano en lugar de usar `QMessageBox.about`
        # para poder marcar los enlaces como pulsables: de otro modo la web y el
        # enlace de donación quedarían como texto muerto.
        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Acerca de ArqueoCAD")
        cuadro.setIconPixmap(self.windowIcon().pixmap(64, 64))
        cuadro.setTextFormat(Qt.TextFormat.RichText)
        cuadro.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        cuadro.setText(
            f"<h3>ArqueoCAD {__version__}</h3>"
            "<p>Lectura de planos DWG, DXF y SVG y separación por capas.</p>"
            "<hr>"
            "<p>Este es un software gratuito y de libre distribución creado por "
            "José Javier Martínez.</p>"
            '<p>Contacto: <a href="https://josejaviermartinez.com">'
            "josejaviermartinez.com</a></p>"
            "<hr>"
            "<p>ArqueoCAD es <b>software libre</b>, distribuido bajo la Licencia "
            "Pública General de GNU, versión 3 "
            '(<a href="https://www.gnu.org/licenses/gpl-3.0.html">GPL-3.0</a>).</p>'
            "<p>Usa la biblioteca <b>Qt 6</b> a través de PySide6 bajo licencia "
            "LGPL-3.0, junto con ezdxf, svgelements, NumPy, pyparsing y fonttools.</p>"
        )
        # El botón abre la carpeta de licencias: la LGPL exige que el usuario
        # pueda consultarlas, y enterrarlas en un archivo de texto que nadie
        # encuentra cumple la letra pero no el propósito.
        boton = cuadro.addButton("Ver las licencias", QMessageBox.ButtonRole.ActionRole)
        cuadro.addButton("Cerrar", QMessageBox.ButtonRole.AcceptRole)
        cuadro.exec()

        if cuadro.clickedButton() is boton:
            self._abrir_licencias()

    def _abrir_licencias(self) -> None:
        """Abre la carpeta de licencias en el explorador del sistema."""
        carpeta = _carpeta_licencias()
        if carpeta is None:
            QMessageBox.warning(
                self,
                "No se encuentran las licencias",
                "La carpeta «licencias» no está junto a la aplicación.\n\n"
                "Los textos pueden consultarse en https://www.gnu.org/licenses/",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(carpeta)))

    @Slot(float, float)
    def _mostrar_coordenadas(self, x: float, y: float) -> None:
        unidad = simbolo(self._documento.unidad) if self._documento else "ud."
        self._etiqueta_coordenadas.setText(f"X {x:,.3f}   Y {y:,.3f} {unidad}".replace(",", " "))

    @Slot(float)
    def _mostrar_escala(self, escala: float) -> None:
        self._etiqueta_escala.setText(f"{escala:,.2f} px/ud.".replace(",", " "))

    # -- arrastrar y soltar ----------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - API de Qt
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - API de Qt
        urls = event.mimeData().urls()
        if urls:
            self.abrir(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._detener_hilo()
        super().closeEvent(event)
