"""Punto de entrada del ejecutable empaquetado.

PyInstaller ejecuta su guion principal como `__main__`, no como módulo dentro
del paquete, de modo que las importaciones relativas de `arqueocad.app` fallan
si se le señala ese archivo directamente. Este lanzador importa el paquete de
forma normal y le cede el control.
"""

from __future__ import annotations

import sys

from arqueocad.app import main

if __name__ == "__main__":
    sys.exit(main())
