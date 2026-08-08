# ArqueoCAD

**Lector de planos y separador de capas para arqueología.**

Abre archivos **DXF**, **SVG** y **DWG**, permite revisar sus capas y obtener
cada una en su propio archivo DXF o SVG, sin alterar la geometría ni la escala.
Pensado para planimetría de excavación.

![Licencia](https://img.shields.io/badge/licencia-GPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Plataformas](https://img.shields.io/badge/plataformas-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

## Qué hace

- Abre planos de AutoCAD (DXF y DWG) y dibujos vectoriales (SVG).
- Muestra las capas con su color, su contenido y un filtro por nombre.
- **Separa el plano en un archivo por capa**, en DXF para seguir trabajando en
  CAD o en SVG con capas de Inkscape para la figura de publicación.
- Procesa **campañas enteras por lotes**, con filtro de capas por comodines
  (`UE-*`, `*_2024`).
- Mide distancias, superficies y acimut sobre el plano.
- Exporta a la escala de publicación que se indique (1:20, 1:50, 1:100…).
- Interfaz en **español e inglés**, conmutable desde `Ver › Idioma`.

## Criterios de diseño

**Nada se pierde en silencio.** Toda simplificación queda registrada como aviso
consultable. Un plano que llega a la publicación con la escala alterada es un
error grave y difícil de detectar a simple vista.

**La exportación a DXF copia las entidades originales** en lugar de
reconstruirlas desde la geometría del visor, de modo que splines, sombreados y
bloques llegan sin pérdida al archivo de salida.

**Una entidad defectuosa no invalida el archivo.** Lo que falla se anota en vez
de interrumpir la lectura.

## Instalación

Descargas para el usuario final en
[josejaviermartinez.com](https://josejaviermartinez.com).

Para ejecutarlo desde el código, con Python 3.12:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m arqueocad.app
```

### Archivos DWG

Los DXF y SVG se abren directamente. Para los **DWG** hace falta instalar
[ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter),
que es gratuito, porque DWG es un formato propietario y cerrado del que no
existe biblioteca libre de lectura completa. ArqueoCAD lo detecta solo.

## Documentación

La documentación técnica —arquitectura, decisiones de diseño, empaquetado y las
trampas encontradas por el camino— está en [LEEME.md](LEEME.md).

## Licencia

ArqueoCAD es software libre bajo la
[GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html). Puede usarse, copiarse,
estudiarse y modificarse. Quien distribuya una versión modificada debe publicar
también su código fuente bajo la misma licencia.

Usa Qt 6 a través de PySide6 (LGPL-3.0), junto con ezdxf, svgelements, NumPy,
pyparsing y fonttools. Los textos completos están en [licencias/](licencias/).

Código fuente: <https://github.com/JJ-Martinez-Garcia/ArqueoCAD>

AutoCAD, DWG y DXF son marcas registradas de Autodesk, Inc. Se mencionan
únicamente para describir la compatibilidad de formatos; este proyecto no está
afiliado a Autodesk ni cuenta con su respaldo.

## Autor

José Javier Martínez García — [josejaviermartinez.com](https://josejaviermartinez.com)
