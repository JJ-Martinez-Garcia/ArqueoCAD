"""Genera el icono de ArqueoCAD.

Dibuja tres capas apiladas y desplazadas —la metáfora de lo que hace el
programa— sobre el fondo oscuro del visor. Se genera por código para no
arrastrar un binario opaco al repositorio y para poder rehacerlo a cualquier
tamaño.

    .venv\\Scripts\\python.exe tools/crear_icono.py
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

#: Tamaños que Windows espera dentro de un .ico.
TAMANIOS = (16, 24, 32, 48, 64, 128, 256)

FONDO = QColor(24, 26, 30)

#: Colores de las tres capas, tomados de la paleta ACI de AutoCAD: rojo, verde
#: y cian son los que más aparecen en planimetría de excavación.
CAPAS = (
    (QColor(0, 255, 255), 0.30),
    (QColor(0, 200, 80), 0.15),
    (QColor(230, 60, 60), 0.00),
)


def dibujar(lado: int) -> QImage:
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)

    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    radio = lado * 0.18
    pintor.setBrush(QBrush(FONDO))
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.drawRoundedRect(0, 0, lado, lado, radio, radio)

    # Cada capa es un rombo aplastado, como una planta vista en perspectiva.
    ancho = lado * 0.62
    alto = lado * 0.26
    centro_x = lado / 2

    for color, desplazamiento in CAPAS:
        centro_y = lado * (0.34 + desplazamiento)
        rombo = QPolygonF(
            [
                QPointF(centro_x, centro_y - alto / 2),
                QPointF(centro_x + ancho / 2, centro_y),
                QPointF(centro_x, centro_y + alto / 2),
                QPointF(centro_x - ancho / 2, centro_y),
            ]
        )

        relleno = QColor(color)
        relleno.setAlpha(70)
        pintor.setBrush(QBrush(relleno))

        pluma = QPen(color)
        pluma.setWidthF(max(1.0, lado * 0.035))
        pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pintor.setPen(pluma)

        pintor.drawPolygon(rombo)

    pintor.end()
    return imagen


def main() -> int:
    QApplication(sys.argv)

    destino = RAIZ / "packaging"
    destino.mkdir(parents=True, exist_ok=True)

    # Cada tamaño se dibuja aparte en lugar de reducir el mayor: a 16 píxeles,
    # un trazo calculado para 256 se convierte en una mancha.
    sueltos = []
    for lado in TAMANIOS:
        imagen = dibujar(lado)
        archivo = destino / f"_icono_{lado}.png"
        imagen.save(str(archivo))
        sueltos.append(archivo)
        if lado == 256:
            imagen.save(str(destino / "arqueocad.png"))

    print(f"PNG: {destino / 'arqueocad.png'}")

    # Qt no escribe .ico, de modo que se compone con Pillow si está disponible;
    # si no, el empaquetado usará el PNG.
    try:
        from PIL import Image
    except ImportError:
        print("Pillow no está instalado: no se genera el .ico")
        return 0

    ico = destino / "arqueocad.ico"
    with Image.open(sueltos[-1]) as mayor:
        mayor.save(ico, format="ICO", sizes=[(t, t) for t in TAMANIOS])
    print(f"ICO: {ico}")

    # Pillow abre los archivos de forma perezosa; hay que cerrarlos antes de
    # borrarlos o Windows impide el borrado.
    for archivo in sueltos:
        archivo.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
