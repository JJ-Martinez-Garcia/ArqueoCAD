"""Traducción de la interfaz entre español e inglés.

Se usa el propio texto español como clave, en lugar de identificadores como
``menu.archivo.abrir``. Tiene dos ventajas que pesan más que la elegancia de un
sistema de claves: el código sigue siendo legible sin consultar el catálogo, y
un texto sin traducir aparece en español en vez de mostrar la clave en crudo.

Las cadenas con datos interpolados se escriben como plantillas y se formatean
después de traducir, porque el orden de las palabras cambia entre idiomas:

    t("{n} capas seleccionadas").format(n=17)
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

#: Idiomas admitidos, con su nombre en su propia lengua.
IDIOMAS = {"es": "Español", "en": "English"}

IDIOMA_POR_DEFECTO = "es"

_actual = IDIOMA_POR_DEFECTO

#: Español → inglés. Lo que no figure aquí se muestra en español, que es la
#: lengua en que está escrita la interfaz.
CATALOGO: dict[str, str] = {
    # -- ventana principal ------------------------------------------------
    "&Archivo": "&File",
    "&Ver": "&View",
    "A&yuda": "&Help",
    "Principal": "Main",
    "&Abrir plano…": "&Open drawing…",
    "Abrir plano": "Open drawing",
    "Separar por &lotes…": "&Batch separation…",
    "&Separar por capas…": "&Separate by layers…",
    "&Salir": "&Quit",
    "Encuadrar &todo": "Zoom to &fit",
    "Encuadrar la &selección": "Zoom to &selection",
    "&Medir": "&Measure",
    "&Conversores de DWG…": "DWG &converters…",
    "Acerca de Arqueo&CAD": "About Arqueo&CAD",
    "&Idioma": "&Language",
    "Capas": "Layers",
    "Ningún plano abierto": "No drawing open",
    "Leyendo {nombre}…": "Reading {nombre}…",
    "Acerca de ArqueoCAD": "About ArqueoCAD",
    "Ver las licencias": "View licences",
    "Cerrar": "Close",
    "Separar": "Separate",
    "Procesar": "Process",
    # -- mensajes de la ventana -------------------------------------------
    "No se ha podido abrir el plano": "The drawing could not be opened",
    "Hace falta un conversor de DWG": "A DWG converter is required",
    "Conversores de DWG": "DWG converters",
    "Ninguna capa seleccionada": "No layer selected",
    "Avisos del archivo": "File warnings",
    "&Avisos del archivo…": "File &warnings…",
    "&Avisos del archivo ({n})…": "File &warnings ({n})…",
    "No se encuentran las licencias": "Licences not found",
    "Se han registrado {n} incidencias al leer el plano.":
        "{n} issues were recorded while reading the drawing.",
    "Seleccione en el panel de capas las que quiere exportar.\n\n"
    "La casilla controla lo que se ve; la selección de filas, lo que se exporta.":
        "Select in the layers panel the ones you want to export.\n\n"
        "The checkbox controls what is displayed; the row selection, what is exported.",
    "La carpeta «licencias» no está junto a la aplicación.\n\n"
    "Los textos pueden consultarse en https://www.gnu.org/licenses/":
        "The «licencias» folder is not next to the application.\n\n"
        "The texts are available at https://www.gnu.org/licenses/",
    "Error inesperado al leer el archivo: {error}":
        "Unexpected error while reading the file: {error}",
    "El archivo se ha abierto con {n} avisos. Consúltalos en Ayuda › Avisos del archivo.":
        "The file was opened with {n} warnings. See Help › File warnings.",
    # -- panel de capas ---------------------------------------------------
    "Capa": "Layer",
    "Entidades": "Entities",
    "Filtrar capas…  (p. ej. UE-1)": "Filter layers…  (e.g. UE-1)",
    "Todas": "All",
    "Ninguna": "None",
    "Invertir": "Invert",
    "Solo esta": "Only this",
    "Mostrar y seleccionar todas las capas": "Show and select every layer",
    "Ocultar y deseleccionar todas": "Hide and deselect all",
    "Invertir la selección actual": "Invert the current selection",
    "Dejar visible únicamente la capa activa": "Leave only the active layer visible",
    "Sin plano cargado": "No drawing loaded",
    "Color ACI {n}": "ACI colour {n}",
    "Tipo de línea: {tipo}": "Line type: {tipo}",
    "Contiene: {tipos}": "Contains: {tipos}",
    "Capa auxiliar del programa de CAD: queda fuera de la exportación.":
        "CAD program helper layer: excluded from export.",
    "Capa vacía.": "Empty layer.",
    "{total} capas · {visibles} visibles · {sel} seleccionadas para exportar ({ent} entidades)":
        "{total} layers · {visibles} visible · {sel} selected for export ({ent} entities)",
    # -- diálogo de exportación -------------------------------------------
    "Separar por capas": "Separate by layers",
    "<b>{n} capas seleccionadas</b> · {ent} entidades":
        "<b>{n} layers selected</b> · {ent} entities",
    "Cómo se reparte": "How it is split",
    "Un archivo por capa": "One file per layer",
    "Un solo archivo con todas las capas": "A single file with every layer",
    "Genera tantos archivos como capas seleccionadas.":
        "Creates as many files as selected layers.",
    "Filtra el plano conservando su estructura.":
        "Filters the drawing while keeping its structure.",
    "Formato de salida": "Output format",
    "DXF — para seguir trabajando en CAD": "DXF — to keep working in CAD",
    "SVG — con capas de Inkscape, para la figura de publicación":
        "SVG — with Inkscape layers, for the published figure",
    "Escala del SVG:": "SVG scale:",
    "Unidad del plano:": "Drawing unit:",
    "Tamaño real (1:1)": "Actual size (1:1)",
    "El plano no declara sus unidades; hay que indicarlas para conservar la escala.":
        "The drawing does not declare its units; they must be set to keep the scale.",
    "Destino": "Destination",
    "Carpeta:": "Folder:",
    "Prefijo:": "Prefix:",
    "Examinar…": "Browse…",
    "Carpeta de destino": "Destination folder",
    "Opciones": "Options",
    "Desplegar los bloques para repartir su geometría por capas":
        "Explode blocks to distribute their geometry across layers",
    "Sin desplegar, un bloque insertado en una capa viaja entero con ella, "
    "aunque su interior pertenezca a otras capas.":
        "Without exploding, a block inserted on a layer travels whole with it, "
        "even if its contents belong to other layers.",
    "Omitir las capas sin entidades": "Skip layers with no entities",
    "Incluir las capas auxiliares del programa de CAD («Defpoints» y las no imprimibles)":
        "Include CAD helper layers («Defpoints» and non-plotting ones)",
    "{n} archivos generados en {carpeta}": "{n} files created in {carpeta}",
    # -- diálogo de lotes -------------------------------------------------
    "Separar por lotes": "Batch separation",
    "Separa varios planos de una campaña con las mismas opciones.":
        "Separates several drawings of a season with the same options.",
    "Planos": "Drawings",
    "Añadir planos…": "Add drawings…",
    "Añadir una carpeta…": "Add a folder…",
    "Quitar": "Remove",
    "Vaciar": "Clear",
    "Añadir planos": "Add drawings",
    "Añadir una carpeta": "Add a folder",
    "También pueden arrastrarse archivos sobre esta ventana.":
        "Files can also be dragged onto this window.",
    "Qué capas se exportan": "Which layers are exported",
    "Patrones:": "Patterns:",
    "todas las capas": "every layer",
    "Se admiten comodines y varios patrones separados por comas. "
    "En blanco, se exportan todas las capas de cada plano.":
        "Wildcards and several comma-separated patterns are allowed. "
        "If left blank, every layer of each drawing is exported.",
    "Salida": "Output",
    "Formatos:": "Formats:",
    "Una subcarpeta por plano": "One subfolder per drawing",
    "Desplegar los bloques": "Explode blocks",
    "No hay planos admitidos en {carpeta}": "No supported drawings in {carpeta}",
    "{correctos} de {total} planos procesados": "{correctos} of {total} drawings processed",
    "{n} archivos generados": "{n} files created",
    "{n} con errores": "{n} with errors",
    # -- vectorización ----------------------------------------------------
    "&Vectorizar imagen…": "&Vectorise image…",
    "Vectorizar imagen": "Vectorise image",
    "Vectorizar": "Vectorise",
    "Vectorizando…": "Vectorising…",
    "Cancelar": "Cancel",
    "Imágenes": "Images",
    "Convierte un plano escaneado o fotografiado en geometría.":
        "Turns a scanned or photographed drawing into geometry.",
    "No se ha podido abrir la imagen": "The image could not be opened",
    "Sin imagen": "No image",
    "Detección del trazo": "Stroke detection",
    "Umbral automático": "Automatic threshold",
    "Umbral:": "Threshold:",
    "Corregir la iluminación desigual": "Correct uneven lighting",
    "Imprescindible en fotografías: sin esto, un umbral único "
    "ennegrece la zona más oscura y blanquea la contraria.":
        "Essential for photographs: without it, a single threshold blackens "
        "the darker area and washes out the other.",
    "El dibujo es claro sobre fondo oscuro": "The drawing is light on a dark background",
    "Manchas menores que:": "Blobs smaller than:",
    "Simplificación:": "Simplification:",
    "Subirla da archivos más ligeros a costa de redondear las esquinas.":
        "Raising it gives lighter files at the cost of rounding corners.",
    "Una sola capa": "A single layer",
    "Por grosor del trazo": "By stroke width",
    "Por color del trazo": "By stroke colour",
    "La separación es gráfica, no de significado: no puede distinguir "
    "un muro de una cota si están dibujados igual.":
        "The split is graphical, not semantic: it cannot tell a wall from a "
        "spot height if they are drawn alike.",
    "Escala": "Scale",
    "Marcar dos puntos…": "Mark two points…",
    "Lo natural es marcar los extremos de la escala gráfica del plano.":
        "The natural choice is the ends of the drawing's own scale bar.",
    "Distancia real:": "Actual distance:",
    "Unidad:": "Unit:",
    "Sin calibrar, el resultado sale en píxeles y no sirve para medir.":
        "Without calibration the result is in pixels and cannot be measured.",
    "Marque dos puntos de distancia conocida sobre la imagen.":
        "Mark two points of known distance on the image.",
    "Marque el segundo punto.": "Mark the second point.",
    "Calibrado: {v} unidades de dibujo por píxel.":
        "Calibrated: {v} drawing units per pixel.",
    "Trazo detectado: {pct} % de la imagen": "Stroke detected: {pct} % of the image",
    # -- medición ---------------------------------------------------------
    "Medición: marque el primer punto": "Measurement: mark the first point",
    "Medición: marque el segundo punto": "Measurement: mark the second point",
    "Longitud: {valor}": "Length: {valor}",
    "Acimut: {valor}°": "Azimuth: {valor}°",
    "Área: {valor}": "Area: {valor}",
    "Perímetro: {valor}": "Perimeter: {valor}",
    "Marque puntos con el botón izquierdo. El derecho retira el último, "
    "Esc limpia la medición y el botón central desplaza el plano.":
        "Mark points with the left button. The right one removes the last, "
        "Esc clears the measurement and the middle button pans the drawing.",
    # -- formatos de archivo ----------------------------------------------
    "Planos admitidos (*.dxf *.dwg *.svg)": "Supported drawings (*.dxf *.dwg *.svg)",
    "Todos los archivos (*)": "All files (*)",
    # -- unidades ---------------------------------------------------------
    #: Abreviatura de «unidades de dibujo», usada cuando el plano no declara las
    #: suyas. En inglés se abrevia «du», de drawing units.
    "ud.": "du",
    "{escala} px/ud.": "{escala} px/du",
    "X {x}   Y {y} {unidad}": "X {x}   Y {y} {unidad}",
    "sin definir": "undefined",
    "milímetros": "millimetres",
    "centímetros": "centimetres",
    "metros": "metres",
    "kilómetros": "kilometres",
    # -- barra de estado --------------------------------------------------
    "{nombre} · {ent} entidades · {capas} capas · unidad: {unidad}":
        "{nombre} · {ent} entities · {capas} layers · unit: {unidad}",
    # -- cambio de idioma -------------------------------------------------
    "El idioma se ha cambiado a {idioma}.": "The language has been changed to {idioma}.",
    "Idioma cambiado": "Language changed",
}


def idioma_actual() -> str:
    return _actual


def fijar_idioma(codigo: str) -> None:
    """Cambia el idioma de la interfaz."""
    global _actual
    _actual = codigo if codigo in IDIOMAS else IDIOMA_POR_DEFECTO


def detectar_del_sistema() -> str:
    """Devuelve el idioma del sistema si está admitido, o el de por defecto."""
    import locale

    try:
        etiqueta = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        etiqueta = ""

    codigo = etiqueta.split("_")[0].casefold()[:2]
    return codigo if codigo in IDIOMAS else IDIOMA_POR_DEFECTO


def t(texto: str) -> str:
    """Traduce un texto al idioma activo.

    Lo que no esté en el catálogo se devuelve tal cual: una interfaz con alguna
    frase sin traducir sigue siendo utilizable, mientras que una que muestre
    claves internas no lo es.
    """
    if _actual == IDIOMA_POR_DEFECTO:
        return texto
    return CATALOGO.get(texto, texto)
