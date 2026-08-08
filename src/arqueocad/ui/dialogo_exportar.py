"""Diálogo de separación y exportación."""

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
    QButtonGroup,
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
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.modelo import Documento
from ..core.separador import Formato, Modo, Opciones, Resultado, separar
from ..core.unidades import Unidad
from ..core.unidades import nombre as nombre_unidad

#: Unidades que se ofrecen cuando el plano no declara la suya. Son las que
#: aparecen en planimetría de excavación; el resto solo añadiría ruido.
UNIDADES_HABITUALES = (
    Unidad.METROS,
    Unidad.CENTIMETROS,
    Unidad.MILIMETROS,
    Unidad.KILOMETROS,
)

#: Escalas de publicación de uso corriente en arqueología.
ESCALAS = (1, 10, 20, 25, 50, 100, 200, 500)


class _Trabajador(QObject):
    """Ejecuta la separación fuera del hilo de la interfaz."""

    avance = Signal(int, int, str)
    terminado = Signal(object)
    fallido = Signal(str)

    def __init__(self, documento: Documento, capas: list[str], opciones: Opciones) -> None:
        super().__init__()
        self._documento = documento
        self._capas = capas
        self._opciones = opciones

    @Slot()
    def ejecutar(self) -> None:
        try:
            resultado = separar(
                self._documento,
                self._capas,
                self._opciones,
                progreso=lambda hechos, total, nombre: self.avance.emit(hechos, total, nombre),
            )
        except Exception as exc:  # noqa: BLE001 - el diálogo debe sobrevivir
            self.fallido.emit(str(exc))
        else:
            self.terminado.emit(resultado)


class DialogoExportar(QDialog):
    """Recoge las opciones de separación y muestra el resultado."""

    def __init__(
        self, documento: Documento, capas: list[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Separar por capas")
        self.setMinimumWidth(560)

        self._documento = documento
        self._capas = capas
        self._hilo: QThread | None = None
        self._trabajador: _Trabajador | None = None
        self._resultado: Resultado | None = None

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self._cabecera())
        disposicion.addWidget(self._grupo_modo())
        disposicion.addWidget(self._grupo_formato())
        disposicion.addWidget(self._grupo_destino())
        disposicion.addWidget(self._grupo_opciones())

        self._progreso = QProgressBar()
        self._progreso.hide()
        disposicion.addWidget(self._progreso)

        self._informe = QListWidget()
        self._informe.hide()
        self._informe.setMaximumHeight(200)
        disposicion.addWidget(self._informe)

        # Los botones se rotulan a mano: los estándar de Qt salen en el idioma
        # del sistema, que no tiene por qué ser el de la aplicación.
        self._botones = QDialogButtonBox()
        self._boton_exportar = self._botones.addButton(
            "Separar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        cerrar = self._botones.addButton("Cerrar", QDialogButtonBox.ButtonRole.RejectRole)
        self._boton_exportar.clicked.connect(self._exportar)
        cerrar.clicked.connect(self.reject)
        disposicion.addWidget(self._botones)

        self._actualizar_disponibilidad()

    # -- construcción ----------------------------------------------------

    def _cabecera(self) -> QLabel:
        entidades = sum(
            self._documento.capas[c].n_entidades
            for c in self._capas
            if c in self._documento.capas
        )
        etiqueta = QLabel(
            f"<b>{len(self._capas)} capas seleccionadas</b> · {entidades:,} entidades".replace(",", ".")
        )
        etiqueta.setWordWrap(True)
        return etiqueta

    def _grupo_modo(self) -> QGroupBox:
        grupo = QGroupBox("Cómo se reparte")
        disposicion = QVBoxLayout(grupo)

        self._modo = QButtonGroup(self)
        opciones = (
            (Modo.POR_CAPA, "Un archivo por capa", "Genera tantos archivos como capas seleccionadas."),
            (Modo.UNICO, "Un solo archivo con todas las capas", "Filtra el plano conservando su estructura."),
        )
        for indice, (modo, titulo, ayuda) in enumerate(opciones):
            boton = QRadioButton(titulo)
            boton.setToolTip(ayuda)
            boton.setChecked(indice == 0)
            self._modo.addButton(boton, indice)
            boton.setProperty("modo", modo.value)
            disposicion.addWidget(boton)

        return grupo

    def _grupo_formato(self) -> QGroupBox:
        grupo = QGroupBox("Formato de salida")
        disposicion = QVBoxLayout(grupo)

        self._dxf = QCheckBox("DXF — para seguir trabajando en CAD")
        self._dxf.setChecked(True)
        self._dxf.toggled.connect(self._actualizar_disponibilidad)
        disposicion.addWidget(self._dxf)

        self._svg = QCheckBox("SVG — con capas de Inkscape, para la figura de publicación")
        self._svg.toggled.connect(self._actualizar_disponibilidad)
        disposicion.addWidget(self._svg)

        self._formulario = QFormLayout()
        self._escala = QComboBox()
        for denominador in ESCALAS:
            self._escala.addItem(
                "Tamaño real (1:1)" if denominador == 1 else f"1:{denominador}", denominador
            )
        self._escala.setCurrentIndex(ESCALAS.index(50))
        self._formulario.addRow("Escala del SVG:", self._escala)

        self._unidad = QComboBox()
        for unidad in UNIDADES_HABITUALES:
            self._unidad.addItem(nombre_unidad(unidad), unidad)
        self._formulario.addRow("Unidad del plano:", self._unidad)
        self._fila_unidad = self._formulario.rowCount() - 1

        self._aviso_unidad = QLabel(
            "El plano no declara sus unidades; hay que indicarlas para conservar la escala."
        )
        self._aviso_unidad.setWordWrap(True)
        self._formulario.addRow(self._aviso_unidad)
        self._fila_aviso = self._formulario.rowCount() - 1

        disposicion.addLayout(self._formulario)
        return grupo

    def _grupo_destino(self) -> QGroupBox:
        grupo = QGroupBox("Destino")
        disposicion = QFormLayout(grupo)

        origen = Path(self._documento.ruta)
        fila = QHBoxLayout()
        self._carpeta = QLineEdit(str(origen.parent / f"{origen.stem}_capas"))
        boton = QPushButton("Examinar…")
        boton.clicked.connect(self._elegir_carpeta)
        fila.addWidget(self._carpeta)
        fila.addWidget(boton)
        disposicion.addRow("Carpeta:", fila)

        self._prefijo = QLineEdit(origen.stem)
        disposicion.addRow("Prefijo:", self._prefijo)

        return grupo

    def _grupo_opciones(self) -> QGroupBox:
        grupo = QGroupBox("Opciones")
        disposicion = QVBoxLayout(grupo)

        self._explotar = QCheckBox("Desplegar los bloques para repartir su geometría por capas")
        self._explotar.setToolTip(
            "Sin desplegar, un bloque insertado en una capa viaja entero con ella, "
            "aunque su interior pertenezca a otras capas."
        )
        disposicion.addWidget(self._explotar)

        self._omitir_vacias = QCheckBox("Omitir las capas sin entidades")
        self._omitir_vacias.setChecked(True)
        disposicion.addWidget(self._omitir_vacias)

        self._incluir_auxiliares = QCheckBox(
            "Incluir las capas auxiliares del programa de CAD («Defpoints» y las no imprimibles)"
        )
        disposicion.addWidget(self._incluir_auxiliares)

        return grupo

    # -- reacciones ------------------------------------------------------

    def _elegir_carpeta(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(
            self, "Carpeta de destino", self._carpeta.text()
        )
        if carpeta:
            self._carpeta.setText(carpeta)

    def _actualizar_disponibilidad(self) -> None:
        con_svg = self._svg.isChecked()
        self._escala.setEnabled(con_svg)

        # Se oculta la fila entera, etiqueta incluida: ocultar solo el desplegable
        # dejaría un rótulo suelto sin nada al lado.
        sin_unidades = self._documento.unidad == Unidad.SIN_DEFINIR
        self._formulario.setRowVisible(self._fila_unidad, con_svg and sin_unidades)
        self._formulario.setRowVisible(self._fila_aviso, con_svg and sin_unidades)
        self._formulario.setRowVisible(0, con_svg)

        self._boton_exportar.setEnabled(self._dxf.isChecked() or con_svg)

    def _opciones(self) -> Opciones:
        formatos = []
        if self._dxf.isChecked():
            formatos.append(Formato.DXF)
        if self._svg.isChecked():
            formatos.append(Formato.SVG)

        boton = self._modo.checkedButton()
        modo = Modo(boton.property("modo")) if boton else Modo.POR_CAPA

        return Opciones(
            carpeta=Path(self._carpeta.text()),
            modo=modo,
            formatos=tuple(formatos),
            prefijo=self._prefijo.text().strip(),
            explotar_bloques=self._explotar.isChecked(),
            omitir_vacias=self._omitir_vacias.isChecked(),
            incluir_auxiliares=self._incluir_auxiliares.isChecked(),
            escala_svg=float(self._escala.currentData()),
            unidad_forzada=(
                self._unidad.currentData()
                if self._documento.unidad == Unidad.SIN_DEFINIR
                else None
            ),
        )

    def _exportar(self) -> None:
        self._informe.clear()
        self._informe.hide()
        self._progreso.setValue(0)
        self._progreso.show()
        self._boton_exportar.setEnabled(False)

        self._hilo = QThread(self)
        self._trabajador = _Trabajador(self._documento, self._capas, self._opciones())
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
    def _al_terminar(self, resultado: Resultado) -> None:
        self._detener_hilo()
        self._resultado = resultado
        self._mostrar_informe(resultado)

    @Slot(str)
    def _al_fallar(self, mensaje: str) -> None:
        self._detener_hilo()
        self._informe.show()
        self._informe.addItem(QListWidgetItem(f"✕  {mensaje}"))

    def _detener_hilo(self) -> None:
        self._progreso.hide()
        self._boton_exportar.setEnabled(True)
        if self._hilo is not None:
            self._hilo.quit()
            self._hilo.wait()
            self._hilo = None
        self._trabajador = None

    def _mostrar_informe(self, resultado: Resultado) -> None:
        self._informe.show()
        carpeta = Path(self._carpeta.text())

        self._informe.addItem(
            QListWidgetItem(
                f"✔  {resultado.total_archivos} archivos generados en {carpeta}"
            )
        )
        for archivo in resultado.archivos:
            self._informe.addItem(
                QListWidgetItem(
                    f"     {archivo.ruta.name}   ·   {archivo.n_entidades} entidades"
                    f"   ·   {archivo.tamanio / 1024:.1f} KB"
                )
            )

        iconos = {"info": "·", "aviso": "▲", "error": "✕"}
        # Los avisos idénticos se repiten una vez por archivo; se agrupan para
        # que el informe siga siendo legible con veinte capas.
        vistos: dict[str, int] = {}
        for aviso in resultado.avisos:
            clave = f"{iconos.get(aviso.nivel, '·')}  {aviso.mensaje}"
            vistos[clave] = vistos.get(clave, 0) + 1

        for mensaje, veces in vistos.items():
            sufijo = f"   (en {veces} archivos)" if veces > 1 else ""
            self._informe.addItem(QListWidgetItem(mensaje + sufijo))

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._detener_hilo()
        super().closeEvent(event)
