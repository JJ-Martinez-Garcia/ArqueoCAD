"""Comprobación de que la interfaz monta y pinta, sin intervención manual.

Carga un plano, monta la ventana completa en modo sin pantalla y guarda una
captura. Sirve para detectar en el acto los fallos de pintado —texto en espejo,
encuadre vacío, colores perdidos— que las pruebas de lectura no pueden ver.

    .venv\\Scripts\\python.exe tools/captura_prueba.py [plano.dxf] [salida.png]
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

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))

# Debe fijarse antes de crear la QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from arqueocad.core.modelo import Documento  # noqa: E402
from arqueocad.io import leer  # noqa: E402
from arqueocad.ui import PanelCapas, VistaPlano  # noqa: E402
from arqueocad.ui.ventana import VentanaPrincipal  # noqa: E402


def main() -> int:
    plano = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "tests" / "plano_prueba.dxf"
    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "tests" / "captura.png"

    if not plano.is_file():
        import plano_de_prueba

        plano_de_prueba.construir(plano)
        print(f"Plano de prueba generado: {plano}")

    aplicacion = QApplication(sys.argv)
    aplicacion.setStyle("Fusion")

    documento: Documento = leer(plano)
    print(f"Leído: {len(documento.entidades)} entidades en {len(documento.capas)} capas")
    print(f"Unidad: {documento.unidad.name}")
    print(f"Extensión: {documento.extension()}")
    for aviso in documento.avisos:
        print(f"  [{aviso.nivel}] {aviso.mensaje}")

    ventana = VentanaPrincipal()
    ventana.resize(1280, 800)
    ventana.show()

    # Se puebla la interfaz sin pasar por el hilo de carga, que en modo sin
    # pantalla no aportaría nada y complicaría la espera.
    vista: VistaPlano = ventana.centralWidget()
    panel: PanelCapas = ventana.findChild(PanelCapas)
    ventana._al_cargar(documento)  # noqa: SLF001 - comprobación interna

    aplicacion.processEvents()
    vista.encuadrar_todo()
    aplicacion.processEvents()

    if not ventana.grab().save(str(salida)):
        print("ERROR: no se ha podido guardar la captura", file=sys.stderr)
        return 1

    print(f"Capas listadas en el panel: {len(panel.capas_visibles())} visibles")
    print(f"Captura: {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
