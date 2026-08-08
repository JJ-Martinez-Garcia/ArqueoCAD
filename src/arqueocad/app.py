"""Punto de entrada de ArqueoCAD.

Ejecución durante el desarrollo:

    .venv\\Scripts\\python.exe -m arqueocad.app [plano.dxf]
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

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Comprobación del ejecutable empaquetado: monta la aplicación entera y sale
    # sin abrir el bucle de eventos. Sin esto no hay forma fiable de saber si un
    # ejecutable sin consola arranca, porque los fallos van a un cuadro de
    # diálogo y el proceso se queda esperando en lugar de terminar con error.
    if "--comprobar" in argv:
        return _comprobar(argv)

    aplicacion = QApplication(argv)
    aplicacion.setApplicationName("ArqueoCAD")
    aplicacion.setApplicationVersion(__version__)
    aplicacion.setOrganizationName("ArqueoCAD")
    # Fusion se ve igual en Windows, macOS y Linux, lo que evita que la
    # aplicación cambie de aspecto según el sistema y facilita el soporte.
    aplicacion.setStyle("Fusion")
    icono = _icono()
    if icono is not None:
        aplicacion.setWindowIcon(icono)

    from .ui import VentanaPrincipal  # se importa tras crear QApplication

    ventana = VentanaPrincipal()
    ventana.show()

    # Permite abrir un plano desde la línea de órdenes o al asociar la
    # extensión .dxf con la aplicación.
    if len(argv) > 1:
        ruta = Path(argv[1])
        if ruta.is_file():
            ventana.abrir(ruta)

    return aplicacion.exec()


def _icono():
    """Carga el icono de la aplicación, esté empaquetada o no.

    En el ejecutable, PyInstaller extrae los datos a una carpeta temporal que
    señala `sys._MEIPASS`; en desarrollo, el archivo está en `packaging/`.
    """
    from PySide6.QtGui import QIcon

    candidatas = []
    empaquetado = getattr(sys, "_MEIPASS", None)
    if empaquetado:
        candidatas.append(Path(empaquetado) / "arqueocad.png")
    candidatas.append(Path(__file__).resolve().parents[2] / "packaging" / "arqueocad.png")

    for ruta in candidatas:
        if ruta.is_file():
            return QIcon(str(ruta))
    return None


def _comprobar(argv: list[str]) -> int:
    """Monta la ventana y, si se indica un plano, lo carga. Luego sale.

    Devuelve 0 si todo ha ido bien. Es lo que ejecuta la comprobación posterior
    al empaquetado, y lo que detectaría que el ejecutable no arranca antes de
    que lo descargue nadie.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    aplicacion = QApplication([argv[0]])
    aplicacion.setStyle("Fusion")
    icono = _icono()
    if icono is not None:
        aplicacion.setWindowIcon(icono)

    from .ui import VentanaPrincipal

    ventana = VentanaPrincipal()
    ventana.resize(1024, 700)
    ventana.show()
    aplicacion.processEvents()

    planos = [a for a in argv[1:] if not a.startswith("--")]
    if planos:
        from .io import leer

        documento = leer(Path(planos[0]))
        print(
            f"{Path(documento.ruta).name}: {len(documento.entidades)} entidades, "
            f"{len(documento.capas)} capas"
        )

    print(f"ArqueoCAD {__version__}: comprobación correcta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
