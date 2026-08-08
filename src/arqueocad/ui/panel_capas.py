"""Panel lateral de capas.

Distingue dos conceptos que conviene no confundir, porque gobiernan cosas
distintas:

- La **casilla de verificación** controla la visibilidad en pantalla.
- La **selección** de filas determina qué capas se exportan.

Se pueden ver capas que no se exportan y al revés, que es justo lo que hace
falta al preparar una separación: mantener a la vista una capa de referencia
—el perímetro del sondeo, por ejemplo— sin incluirla en cada archivo de salida.
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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.modelo import Documento

#: Rol donde se guarda el nombre real de la capa, que no siempre coincide con
#: lo que se muestra.
ROL_NOMBRE = Qt.ItemDataRole.UserRole


class PanelCapas(QWidget):
    """Lista de capas con visibilidad, filtro y selección para exportar."""

    visibilidad_cambiada = Signal()
    seleccion_cambiada = Signal(list)
    encuadre_pedido = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._documento: Documento | None = None
        self._bloqueado = False  # evita reentrar al repoblar el árbol

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(6, 6, 6, 6)
        disposicion.setSpacing(6)

        self._filtro = QLineEdit()
        self._filtro.setPlaceholderText("Filtrar capas…  (p. ej. UE-1)")
        self._filtro.setClearButtonEnabled(True)
        self._filtro.textChanged.connect(self._aplicar_filtro)
        disposicion.addWidget(self._filtro)

        disposicion.addLayout(self._construir_botones())

        self._arbol = QTreeWidget()
        self._arbol.setColumnCount(2)
        self._arbol.setHeaderLabels(["Capa", "Entidades"])
        self._arbol.setRootIsDecorated(False)
        self._arbol.setAlternatingRowColors(True)
        self._arbol.setUniformRowHeights(True)
        self._arbol.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._arbol.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._arbol.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._arbol.itemChanged.connect(self._al_cambiar_casilla)
        self._arbol.itemSelectionChanged.connect(self._al_cambiar_seleccion)
        self._arbol.itemDoubleClicked.connect(self._al_doble_clic)
        disposicion.addWidget(self._arbol, stretch=1)

        self._resumen = QLabel("Sin plano cargado")
        self._resumen.setWordWrap(True)
        disposicion.addWidget(self._resumen)

    def _construir_botones(self) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(4)
        for texto, ayuda, accion in (
            ("Todas", "Mostrar y seleccionar todas las capas", self.seleccionar_todas),
            ("Ninguna", "Ocultar y deseleccionar todas", self.seleccionar_ninguna),
            ("Invertir", "Invertir la selección actual", self.invertir_seleccion),
            ("Solo esta", "Dejar visible únicamente la capa activa", self.aislar),
        ):
            boton = QToolButton()
            boton.setText(texto)
            boton.setToolTip(ayuda)
            boton.clicked.connect(accion)
            fila.addWidget(boton)
        fila.addStretch(1)
        return fila

    # -- carga -----------------------------------------------------------

    def cargar(self, documento: Documento | None) -> None:
        self._documento = documento
        self._bloqueado = True
        self._arbol.clear()

        if documento is None:
            self._resumen.setText("Sin plano cargado")
            self._bloqueado = False
            return

        for nombre in documento.nombres_de_capa():
            capa = documento.capas[nombre]
            item = QTreeWidgetItem([nombre, f"{capa.n_entidades:,}".replace(",", ".")])
            item.setData(0, ROL_NOMBRE, nombre)
            item.setIcon(0, _muestra_de_color(capa.color))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked if capa.dibujable else Qt.CheckState.Unchecked,
            )
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            detalle = [f"Color ACI {capa.aci}", f"Tipo de línea: {capa.tipo_linea}"]
            if capa.tipos_presentes:
                detalle.append("Contiene: " + ", ".join(sorted(capa.tipos_presentes)))
            if capa.auxiliar:
                detalle.append(
                    "Capa auxiliar del programa de CAD: queda fuera de la exportación."
                )
                item.setForeground(0, QColor(150, 150, 150))
            if capa.n_entidades == 0:
                detalle.append("Capa vacía.")
            item.setToolTip(0, "\n".join(detalle))

            self._arbol.addTopLevelItem(item)

        self._bloqueado = False
        # Por defecto se preseleccionan las capas con contenido real, que es lo
        # que el usuario querrá exportar en la mayoría de los casos.
        self.seleccionar_todas()
        self._actualizar_resumen()

    # -- acciones --------------------------------------------------------

    def seleccionar_todas(self) -> None:
        self._para_cada(lambda item: item.setCheckState(0, Qt.CheckState.Checked))
        self._arbol.clearSelection()
        for item in self._items():
            if not self._es_auxiliar(item) and not item.isHidden():
                item.setSelected(True)
        self._emitir()

    def seleccionar_ninguna(self) -> None:
        self._para_cada(lambda item: item.setCheckState(0, Qt.CheckState.Unchecked))
        self._arbol.clearSelection()
        self._emitir()

    def invertir_seleccion(self) -> None:
        for item in self._items():
            if not item.isHidden():
                item.setSelected(not item.isSelected())
        self._emitir()

    def aislar(self) -> None:
        """Deja visible solo la capa activa. Útil para comprobar qué contiene."""
        activo = self._arbol.currentItem()
        if activo is None:
            return
        self._bloqueado = True
        for item in self._items():
            item.setCheckState(
                0,
                Qt.CheckState.Checked if item is activo else Qt.CheckState.Unchecked,
            )
        self._bloqueado = False
        self.visibilidad_cambiada.emit()
        self._actualizar_resumen()

    # -- consultas -------------------------------------------------------

    def capas_seleccionadas(self) -> list[str]:
        return [item.data(0, ROL_NOMBRE) for item in self._arbol.selectedItems()]

    def capas_visibles(self) -> list[str]:
        return [
            item.data(0, ROL_NOMBRE)
            for item in self._items()
            if item.checkState(0) == Qt.CheckState.Checked
        ]

    # -- reacciones ------------------------------------------------------

    def _al_cambiar_casilla(self, item: QTreeWidgetItem, columna: int) -> None:
        if self._bloqueado or self._documento is None or columna != 0:
            return
        capa = self._documento.capas.get(item.data(0, ROL_NOMBRE))
        if capa is None:
            return
        visible = item.checkState(0) == Qt.CheckState.Checked
        capa.visible = visible
        # Una capa congelada no se dibuja aunque se marque; al activarla
        # explícitamente se entiende que se quiere ver.
        if visible:
            capa.congelada = False
        self.visibilidad_cambiada.emit()
        self._actualizar_resumen()

    def _al_cambiar_seleccion(self) -> None:
        self._emitir()

    def _al_doble_clic(self, item: QTreeWidgetItem, columna: int) -> None:
        self.encuadre_pedido.emit([item.data(0, ROL_NOMBRE)])

    def _aplicar_filtro(self, texto: str) -> None:
        patron = texto.strip().casefold()
        for item in self._items():
            item.setHidden(bool(patron) and patron not in item.text(0).casefold())
        self._actualizar_resumen()

    # -- auxiliares ------------------------------------------------------

    def _items(self) -> list[QTreeWidgetItem]:
        return [
            self._arbol.topLevelItem(i) for i in range(self._arbol.topLevelItemCount())
        ]

    def _para_cada(self, funcion) -> None:
        self._bloqueado = True
        for item in self._items():
            if not item.isHidden():
                funcion(item)
        self._bloqueado = False
        self.visibilidad_cambiada.emit()
        self._sincronizar_visibilidad()

    def _sincronizar_visibilidad(self) -> None:
        if self._documento is None:
            return
        for item in self._items():
            capa = self._documento.capas.get(item.data(0, ROL_NOMBRE))
            if capa is not None:
                capa.visible = item.checkState(0) == Qt.CheckState.Checked
                if capa.visible:
                    capa.congelada = False

    def _es_auxiliar(self, item: QTreeWidgetItem) -> bool:
        if self._documento is None:
            return False
        capa = self._documento.capas.get(item.data(0, ROL_NOMBRE))
        return capa is not None and capa.auxiliar

    def _emitir(self) -> None:
        if not self._bloqueado:
            self.seleccion_cambiada.emit(self.capas_seleccionadas())
            self._actualizar_resumen()

    def _actualizar_resumen(self) -> None:
        if self._documento is None:
            return
        total = len(self._documento.capas)
        visibles = len(self.capas_visibles())
        seleccionadas = len(self.capas_seleccionadas())
        entidades = sum(
            self._documento.capas[n].n_entidades for n in self.capas_seleccionadas()
        )
        self._resumen.setText(
            f"{total} capas · {visibles} visibles · "
            f"{seleccionadas} seleccionadas para exportar "
            f"({entidades:,} entidades)".replace(",", ".")
        )


def _muestra_de_color(rgb: tuple[int, int, int]) -> QIcon:
    """Cuadro de color de la capa, con borde para que el negro no desaparezca."""
    lado = 12
    pixmap = QPixmap(QSize(lado, lado))
    pixmap.fill(QColor(*rgb))
    return QIcon(pixmap)
