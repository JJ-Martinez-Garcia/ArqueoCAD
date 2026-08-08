"""Diálogo de separación por lotes.

Pensado para el trabajo de campaña: se añaden todos los planos, se fija una vez
el criterio de separación y se ejecuta. El filtro de capas admite comodines
porque en un lote no se sabe qué capas trae cada archivo, pero sí qué familias
interesan: ``UE-*``, ``*_2024``, ``MURO*``.
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

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.idioma import t
from ..core.lotes import OpcionesLote, ResultadoLote, procesar_lote
from ..core.separador import Formato, Modo, Opciones
from ..io import EXTENSIONES

def _filtro() -> str:
    """Filtro del diálogo de apertura, en el idioma activo."""
    return (
        f"{t('Planos admitidos (*.dxf *.dwg *.svg)')};;"
        "AutoCAD DXF (*.dxf);;AutoCAD DWG (*.dwg);;SVG (*.svg)"
    )

ESCALAS = (1, 10, 20, 25, 50, 100, 200, 500)


class _Trabajador(QObject):
    avance = Signal(int, int, str)
    terminado = Signal(object)
    fallido = Signal(str)

    def __init__(self, rutas: list[Path], opciones: OpcionesLote) -> None:
        super().__init__()
        self._rutas = rutas
        self._opciones = opciones
        self._cancelado = False

    def cancelar(self) -> None:
        self._cancelado = True

    @Slot()
    def ejecutar(self) -> None:
        try:
            resultado = procesar_lote(
                self._rutas,
                self._opciones,
                progreso=lambda h, t, n: self.avance.emit(h, t, n),
                cancelado=lambda: self._cancelado,
            )
        except Exception as exc:  # noqa: BLE001
            self.fallido.emit(str(exc))
        else:
            self.terminado.emit(resultado)


class DialogoLotes(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("Separar por lotes"))
        self.setMinimumWidth(640)
        self.setAcceptDrops(True)

        self._hilo: QThread | None = None
        self._trabajador: _Trabajador | None = None

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self._grupo_planos())
        disposicion.addWidget(self._grupo_capas())
        disposicion.addWidget(self._grupo_salida())

        self._progreso = QProgressBar()
        self._progreso.hide()
        disposicion.addWidget(self._progreso)

        self._informe = QListWidget()
        self._informe.hide()
        self._informe.setMaximumHeight(180)
        disposicion.addWidget(self._informe)

        botones = QDialogButtonBox()
        self._boton_procesar = botones.addButton(
            t("Procesar"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        cerrar = botones.addButton(t("Cerrar"), QDialogButtonBox.ButtonRole.RejectRole)
        self._boton_procesar.clicked.connect(self._procesar)
        cerrar.clicked.connect(self.reject)
        disposicion.addWidget(botones)

        self._actualizar_disponibilidad()

    # -- construcción ----------------------------------------------------

    def _grupo_planos(self) -> QGroupBox:
        grupo = QGroupBox(t("Planos"))
        disposicion = QVBoxLayout(grupo)

        self._lista = QListWidget()
        self._lista.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._lista.setMaximumHeight(140)
        self._lista.model().rowsInserted.connect(self._actualizar_disponibilidad)
        self._lista.model().rowsRemoved.connect(self._actualizar_disponibilidad)
        disposicion.addWidget(self._lista)

        fila = QHBoxLayout()
        for texto, accion in (
            (t("Añadir planos…"), self._anadir_archivos),
            (t("Añadir una carpeta…"), self._anadir_carpeta),
            (t("Quitar"), self._quitar),
            (t("Vaciar"), self._lista.clear),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(accion)
            fila.addWidget(boton)
        fila.addStretch(1)
        disposicion.addLayout(fila)

        ayuda = QLabel(t("También pueden arrastrarse archivos sobre esta ventana."))
        disposicion.addWidget(ayuda)

        return grupo

    def _grupo_capas(self) -> QGroupBox:
        grupo = QGroupBox(t("Qué capas se exportan"))
        disposicion = QFormLayout(grupo)

        self._patrones = QLineEdit()
        self._patrones.setPlaceholderText(t("todas las capas"))
        self._patrones.setToolTip(
            "Patrones separados por comas, con comodines.\n"
            "Ejemplos:  UE-*    *_2024    MURO*, SARCÓFAGO*"
        )
        disposicion.addRow(t("Patrones:"), self._patrones)

        ayuda = QLabel(
            t(
                "Se admiten comodines y varios patrones separados por comas. "
                "En blanco, se exportan todas las capas de cada plano."
            )
        )
        ayuda.setWordWrap(True)
        disposicion.addRow(ayuda)

        return grupo

    def _grupo_salida(self) -> QGroupBox:
        grupo = QGroupBox(t("Salida"))
        disposicion = QFormLayout(grupo)

        fila = QHBoxLayout()
        self._carpeta = QLineEdit()
        boton = QPushButton("Examinar…")
        boton.clicked.connect(self._elegir_carpeta)
        fila.addWidget(self._carpeta)
        fila.addWidget(boton)
        disposicion.addRow(t("Carpeta:"), fila)

        formatos = QHBoxLayout()
        self._dxf = QCheckBox("DXF")
        self._dxf.setChecked(True)
        self._dxf.toggled.connect(self._actualizar_disponibilidad)
        self._svg = QCheckBox("SVG")
        self._svg.toggled.connect(self._actualizar_disponibilidad)
        formatos.addWidget(self._dxf)
        formatos.addWidget(self._svg)
        formatos.addStretch(1)
        disposicion.addRow(t("Formatos:"), formatos)

        self._escala = QComboBox()
        for denominador in ESCALAS:
            self._escala.addItem(
                t("Tamaño real (1:1)") if denominador == 1 else f"1:{denominador}",
                denominador,
            )
        self._escala.setCurrentIndex(ESCALAS.index(50))
        disposicion.addRow(t("Escala del SVG:"), self._escala)
        self._fila_escala = disposicion.rowCount() - 1
        self._formulario = disposicion

        self._subcarpetas = QCheckBox(t("Una subcarpeta por plano"))
        self._subcarpetas.setChecked(True)
        disposicion.addRow(self._subcarpetas)

        self._explotar = QCheckBox(t("Desplegar los bloques"))
        disposicion.addRow(self._explotar)

        return grupo

    # -- planos ----------------------------------------------------------

    def _anadir_archivos(self) -> None:
        rutas, _ = QFileDialog.getOpenFileNames(self, t("Añadir planos"), "", _filtro())
        self._anadir(Path(r) for r in rutas)

    def _anadir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, t("Añadir una carpeta"))
        if not carpeta:
            return
        encontrados = [
            p for p in sorted(Path(carpeta).iterdir())
            if p.is_file() and p.suffix.casefold() in EXTENSIONES
        ]
        if not encontrados:
            self._informe.show()
            self._informe.addItem(
                QListWidgetItem("▲  " + t("No hay planos admitidos en {carpeta}").format(carpeta=carpeta))
            )
            return
        self._anadir(encontrados)

    def _anadir(self, rutas) -> None:
        existentes = {
            self._lista.item(i).text() for i in range(self._lista.count())
        }
        for ruta in rutas:
            if str(ruta) not in existentes:
                self._lista.addItem(str(ruta))

        # La carpeta de salida se propone junto al primer plano, que es donde el
        # usuario espera encontrar el resultado.
        if not self._carpeta.text() and self._lista.count():
            primero = Path(self._lista.item(0).text())
            self._carpeta.setText(str(primero.parent / "capas_separadas"))

    def _quitar(self) -> None:
        for item in self._lista.selectedItems():
            self._lista.takeItem(self._lista.row(item))

    def _elegir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(
            self, t("Carpeta de destino"), self._carpeta.text()
        )
        if carpeta:
            self._carpeta.setText(carpeta)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - API de Qt
        rutas = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        self._anadir(
            r for r in rutas if r.is_file() and r.suffix.casefold() in EXTENSIONES
        )
        event.acceptProposedAction()

    # -- ejecución -------------------------------------------------------

    def _actualizar_disponibilidad(self) -> None:
        self._formulario.setRowVisible(self._fila_escala, self._svg.isChecked())
        self._boton_procesar.setEnabled(
            self._lista.count() > 0 and (self._dxf.isChecked() or self._svg.isChecked())
        )

    def _opciones(self) -> OpcionesLote:
        formatos = []
        if self._dxf.isChecked():
            formatos.append(Formato.DXF)
        if self._svg.isChecked():
            formatos.append(Formato.SVG)

        patrones = [p.strip() for p in self._patrones.text().split(",") if p.strip()]

        return OpcionesLote(
            separacion=Opciones(
                carpeta=Path(self._carpeta.text()),
                modo=Modo.POR_CAPA,
                formatos=tuple(formatos),
                explotar_bloques=self._explotar.isChecked(),
                escala_svg=float(self._escala.currentData()),
            ),
            patrones=patrones,
            subcarpeta_por_plano=self._subcarpetas.isChecked(),
        )

    def _procesar(self) -> None:
        rutas = [
            Path(self._lista.item(i).text()) for i in range(self._lista.count())
        ]
        self._informe.clear()
        self._informe.hide()
        self._progreso.setValue(0)
        self._progreso.show()
        self._boton_procesar.setEnabled(False)

        self._hilo = QThread(self)
        self._trabajador = _Trabajador(rutas, self._opciones())
        self._trabajador.moveToThread(self._hilo)
        self._hilo.started.connect(self._trabajador.ejecutar)
        self._trabajador.avance.connect(self._al_avanzar)
        self._trabajador.terminado.connect(self._al_terminar)
        self._trabajador.fallido.connect(self._al_fallar)
        self._hilo.start()

    @Slot(int, int, str)
    def _al_avanzar(self, hechos: int, total: int, nombre: str) -> None:
        self._progreso.setMaximum(max(total, 1))
        self._progreso.setValue(hechos)
        self._progreso.setFormat(f"%v de %m · {nombre}" if nombre else "%v de %m")

    @Slot(object)
    def _al_terminar(self, resultado: ResultadoLote) -> None:
        self._detener()
        self._informe.show()
        self._informe.addItem(QListWidgetItem(f"✔  {resultado.resumen()}"))

        for plano in resultado.planos:
            if plano.correcto:
                self._informe.addItem(
                    QListWidgetItem(
                        f"     {plano.ruta.name}   ·   {plano.n_capas} capas"
                        f"   ·   {len(plano.archivos)} archivos"
                    )
                )
            else:
                self._informe.addItem(
                    QListWidgetItem(f"✕  {plano.ruta.name}   ·   {plano.error}")
                )

    @Slot(str)
    def _al_fallar(self, mensaje: str) -> None:
        self._detener()
        self._informe.show()
        self._informe.addItem(QListWidgetItem(f"✕  {mensaje}"))

    def _detener(self) -> None:
        self._progreso.hide()
        self._actualizar_disponibilidad()
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait()
            self._hilo = None
        self._trabajador = None

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._trabajador is not None:
            self._trabajador.cancelar()
        self._detener()
        super().closeEvent(event)
