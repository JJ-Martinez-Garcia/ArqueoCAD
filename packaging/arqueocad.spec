# -*- mode: python ; coding: utf-8 -*-
"""Configuración de PyInstaller para ArqueoCAD.

Se ejecuta desde la raíz del proyecto:

    .venv\\Scripts\\python.exe -m PyInstaller packaging/arqueocad.spec --noconfirm

PySide6 arrastra el Qt completo, del que ArqueoCAD usa una parte pequeña. Las
exclusiones de más abajo son la diferencia entre un instalador de 300 MB y uno
de 80, y ninguna afecta a lo que la aplicación hace: se descartan el motor web,
el 3D, el multimedia y los enlaces con bases de datos.
"""

import sys
from pathlib import Path

RAIZ = Path(SPECPATH).parent

#: Módulos de Qt que no se usan. Recortarlos reduce el paquete a menos de la
#: mitad y acorta el arranque en frío.
QT_SOBRANTE = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtQml",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSerialPort",
    "PySide6.QtSensors", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
]

#: Bibliotecas científicas que ezdxf importa solo para funciones que ArqueoCAD
#: no usa. matplotlib por sí solo pesa más que el resto de la aplicación.
OTROS_SOBRANTES = [
    "matplotlib", "scipy", "pandas", "IPython", "notebook", "jupyter",
    "tkinter", "pydoc_data", "setuptools", "pip",
    "PIL",  # solo se usa al generar el icono, no en tiempo de ejecución
]

# `unittest` NO puede excluirse: `pyparsing.testing` lo importa al cargarse, y
# ezdxf depende de pyparsing. Quitarlo produce un ejecutable que se construye
# sin errores y luego no arranca.

icono = RAIZ / "packaging" / ("arqueocad.ico" if sys.platform == "win32" else "arqueocad.png")

analisis = Analysis(
    # Se apunta al lanzador y no a `app.py`: PyInstaller ejecuta su guion
    # principal como `__main__`, y las importaciones relativas del paquete
    # fallarían.
    [str(RAIZ / "packaging" / "lanzador.py")],
    pathex=[str(RAIZ / "src")],
    binaries=[],
    # El icono viaja como dato además de incrustarse en el ejecutable: la
    # ventana y el cuadro «Acerca de» lo cargan en tiempo de ejecución.
    datas=[(str(RAIZ / "packaging" / "arqueocad.png"), ".")],
    hiddenimports=["arqueocad.ui", "arqueocad.io", "arqueocad.core", "cv2"],
    hookspath=[],
    runtime_hooks=[],
    excludes=QT_SOBRANTE + OTROS_SOBRANTES,
    noarchive=False,
)

#: Binarios que PyInstaller arrastra como dependencia declarada de Qt pero que
#: esta aplicación no llega a cargar. Se filtran a mano porque `excludes` solo
#: actúa sobre módulos de Python, no sobre las bibliotecas nativas.
#:
#: - `opengl32sw` es el rasterizador OpenGL por software: ArqueoCAD dibuja con
#:   QPainter sobre el motor raster y nunca lo pide.
#: - Quick y QML son el motor declarativo de interfaces; aquí todo es QtWidgets.
BINARIOS_SOBRANTES = (
    # Códecs de vídeo de OpenCV: casi 30 MB para leer películas, algo que esta
    # aplicación no hace. Las imágenes fijas no pasan por ellos.
    "opencv_videoio_ffmpeg",
    "opengl32sw",
    "qt6quick",
    "qt6qml",
    "qt6qmlmodels",
    "qt6qmlmeta",
    "qt6qmlworkerscript",
)


def _sobra(destino: str) -> bool:
    nombre = Path(destino).name.casefold()
    return any(nombre.startswith(p) for p in BINARIOS_SOBRANTES)


analisis.binaries = TOC(
    (destino, origen, tipo)
    for destino, origen, tipo in analisis.binaries
    if not _sobra(destino)
)

pyz = PYZ(analisis.pure)

ejecutable = EXE(
    pyz,
    analisis.scripts,
    [],
    exclude_binaries=True,
    name="ArqueoCAD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX dispara falsos positivos en los antivirus
    console=False,      # aplicación gráfica: sin ventana de consola
    icon=str(icono) if icono.is_file() else None,
)

coleccion = COLLECT(
    ejecutable,
    analisis.binaries,
    analisis.datas,
    strip=False,
    upx=False,
    name="ArqueoCAD",
)

if sys.platform == "darwin":
    # En macOS el ejecutable suelto no sirve: hace falta un paquete .app para
    # que el sistema lo reconozca como aplicación.
    app = BUNDLE(
        coleccion,
        name="ArqueoCAD.app",
        icon=str(icono) if icono.is_file() else None,
        bundle_identifier="com.josejaviermartinez.arqueocad",
        info_plist={
            "CFBundleDisplayName": "ArqueoCAD",
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Plano CAD",
                    "CFBundleTypeExtensions": ["dxf", "dwg", "svg"],
                    "CFBundleTypeRole": "Viewer",
                }
            ],
        },
    )
