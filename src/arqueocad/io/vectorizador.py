"""Vectorización de planos raster: de imagen a geometría.

Aquí ArqueoCAD deja de traducir y empieza a interpretar, y conviene tenerlo
presente: un DXF dice exactamente dónde empieza y acaba cada línea, mientras que
una imagen es una rejilla de puntos de la que hay que **deducir** los trazos.
Toda deducción acierta a veces y se equivoca otras, de modo que el resultado
siempre habrá que revisarlo. Por eso el vectorizado informa de cuánto ha
descartado y de qué decisiones ha tomado.

El recorrido es:

1. **Corregir la iluminación.** Una fotografía de un plano impreso llega más
   oscura por un lado; sin corregirlo, un umbral único convierte esa zona en una
   mancha negra y pierde la contraria.
2. **Binarizar** separando trazo de fondo.
3. **Limpiar** las motas de grano y polvo del papel.
4. **Adelgazar** el trazo hasta dejarlo de un píxel de ancho. Sin esto, cada
   línea del dibujo saldría como dos líneas paralelas —los dos bordes de su
   trazo—, que es el error clásico de la vectorización por contornos.
5. **Seguir los caminos** del esqueleto para convertirlos en polilíneas.
6. **Simplificar** los vértices redundantes.
7. **Repartir en capas** según la estrategia elegida.
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

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

from ..core.geometria import Punto2D
from ..core.modelo import Aviso, Capa, Documento, FormatoOrigen, Polilinea
from ..core.unidades import Unidad


class EstrategiaCapas(str, Enum):
    """Cómo se reparte en capas lo que se encuentra en la imagen.

    Una imagen no tiene capas: hay que deducirlas de sus características
    gráficas. Ninguna estrategia puede distinguir un muro de una cota si ambos
    están dibujados igual.
    """

    #: Todo a una sola capa. Lo más predecible; la separación se hace luego.
    UNICA = "unica"
    #: Una capa por color del trazo. Fiable cuando el plano usa color.
    COLOR = "color"
    #: Separa trazos finos de gruesos, que suelen codificar contorno y detalle.
    GROSOR = "grosor"


class VectorizacionError(Exception):
    """La imagen no ha podido vectorizarse."""


@dataclass
class OpcionesVectorizado:
    """Ajustes del vectorizado."""

    estrategia: EstrategiaCapas = EstrategiaCapas.UNICA

    #: Umbral de binarización, de 0 a 255. Con ``None`` se calcula solo.
    umbral: int | None = None

    #: Corrige la iluminación desigual antes de binarizar. Imprescindible en
    #: fotografías; inofensivo en escaneados limpios.
    corregir_iluminacion: bool = True

    #: Traza oscura sobre fondo claro, que es lo normal en un plano. Se invierte
    #: para negativos o dibujos en blanco sobre negro.
    trazo_oscuro: bool = True

    #: Área mínima de una mancha para no considerarse suciedad, en píxeles.
    area_minima: int = 12

    #: Longitud mínima de una polilínea para conservarse, en píxeles. Descarta
    #: los restos de grano que sobreviven a la limpieza.
    longitud_minima: float = 8.0

    #: Desviación máxima al simplificar, en píxeles. Subirla da archivos más
    #: ligeros a costa de redondear las esquinas.
    tolerancia: float = 1.0

    #: Unidades de dibujo por píxel. Se obtiene de la calibración.
    escala: float = 1.0
    unidad: Unidad = Unidad.SIN_DEFINIR

    #: Número de colores en que se agrupa la imagen (estrategia COLOR).
    n_colores: int = 4

    #: Frontera entre fino y grueso, en píxeles (estrategia GROSOR). Con
    #: ``None`` se toma la mediana de los grosores encontrados.
    umbral_grosor: float | None = None


@dataclass
class ResultadoVectorizado:
    documento: Documento
    #: Imagen binaria resultante, para previsualizar en la interfaz.
    binaria: np.ndarray | None = field(default=None, repr=False)
    n_trazos: int = 0
    n_descartados: int = 0


def vectorizar(
    ruta: str | Path, opciones: OpcionesVectorizado | None = None
) -> ResultadoVectorizado:
    """Convierte una imagen en un `Documento` con geometría vectorial."""
    import cv2

    opciones = opciones or OpcionesVectorizado()
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo: {ruta}")

    # `imdecode` en vez de `imread`: este último falla con rutas que llevan
    # acentos o eñes en Windows, y los nombres de campaña los llevan.
    datos = np.fromfile(str(ruta), dtype=np.uint8)
    imagen = cv2.imdecode(datos, cv2.IMREAD_COLOR)
    if imagen is None:
        raise VectorizacionError(
            f"«{ruta.name}» no es una imagen que se pueda leer."
        )

    documento = Documento(
        ruta=str(ruta), formato=FormatoOrigen.RASTER, unidad=opciones.unidad
    )
    alto, ancho = imagen.shape[:2]

    documento.avisos.append(
        Aviso(
            "info",
            f"Imagen de {ancho} × {alto} píxeles vectorizada.",
            "El resultado procede de interpretar la imagen y conviene revisarlo: "
            "no hay un original vectorial con el que contrastarlo.",
        )
    )

    if opciones.unidad == Unidad.SIN_DEFINIR:
        documento.avisos.append(
            Aviso(
                "aviso",
                "El dibujo no tiene escala real: las coordenadas están en píxeles.",
                "Para obtener medidas verdaderas hay que calibrar indicando la "
                "distancia entre dos puntos conocidos del plano.",
            )
        )

    if opciones.estrategia is EstrategiaCapas.COLOR:
        capas = _separar_por_color(imagen, opciones, documento)
    else:
        binaria = _binarizar(imagen, opciones, documento)
        if opciones.estrategia is EstrategiaCapas.GROSOR:
            capas = _separar_por_grosor(binaria, opciones, documento)
        else:
            capas = {"IMAGEN": binaria}

    total = 0
    descartados = 0
    ultima_binaria = None

    for nombre, mascara in capas.items():
        ultima_binaria = mascara
        polilineas, fuera = _trazos_de(mascara, opciones)
        descartados += fuera

        if nombre not in documento.capas:
            documento.capas[nombre] = Capa(nombre=nombre)

        for puntos in polilineas:
            documento.entidades.append(
                Polilinea(
                    capa=nombre,
                    tipo_origen="TRAZO",
                    puntos=[_a_dibujo(p, alto, opciones.escala) for p in puntos],
                    cerrada=False,
                )
            )
            total += 1

    if descartados:
        documento.avisos.append(
            Aviso(
                "info",
                f"Se han descartado {descartados} trazos por debajo de la longitud mínima.",
                "Suelen ser grano del papel o restos de la trama de impresión.",
            )
        )

    if not total:
        documento.avisos.append(
            Aviso(
                "error",
                "No se ha encontrado ningún trazo en la imagen.",
                "Puede que el umbral no sea el adecuado o que el dibujo sea claro "
                "sobre fondo oscuro, en cuyo caso hay que invertirlo.",
            )
        )

    documento.recalcular_estadisticas()
    return ResultadoVectorizado(
        documento=documento,
        binaria=ultima_binaria,
        n_trazos=total,
        n_descartados=descartados,
    )


# -- preparación de la imagen -------------------------------------------


def _binarizar(imagen, opciones: OpcionesVectorizado, documento: Documento):
    """Separa trazo de fondo, corrigiendo antes la iluminación si procede."""
    import cv2

    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)

    if opciones.corregir_iluminacion:
        gris = _igualar_fondo(gris)

    if opciones.umbral is None:
        # Otsu elige el umbral que mejor separa los dos grupos de intensidad.
        umbral, binaria = cv2.threshold(
            gris, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        documento.avisos.append(
            Aviso("info", f"Umbral calculado automáticamente: {int(umbral)}.")
        )
    else:
        _, binaria = cv2.threshold(
            gris, opciones.umbral, 255, cv2.THRESH_BINARY_INV
        )

    if not opciones.trazo_oscuro:
        binaria = cv2.bitwise_not(binaria)

    return _quitar_motas(binaria, opciones.area_minima)


def _igualar_fondo(gris):
    """Compensa que una parte de la imagen esté más oscura que otra.

    Se estima el fondo con un desenfoque muy amplio —a esa escala el trazo
    desaparece y solo queda la iluminación— y se divide la imagen por él. Sin
    esto, en una fotografía el umbral único ennegrece una esquina y blanquea la
    contraria.
    """
    import cv2

    # El núcleo ha de ser bastante mayor que el trazo más grueso, o se comería
    # el propio dibujo.
    lado = max(gris.shape) // 8 | 1
    fondo = cv2.GaussianBlur(gris, (lado, lado), 0)

    normalizada = cv2.divide(gris, fondo, scale=255)
    return normalizada


def _quitar_motas(binaria, area_minima: int):
    """Elimina las manchas menores que el área indicada."""
    import cv2

    n, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(
        binaria, connectivity=8
    )
    if n <= 1:
        return binaria

    areas = estadisticas[:, cv2.CC_STAT_AREA]
    conservar = np.zeros(n, dtype=bool)
    conservar[1:] = areas[1:] >= area_minima
    conservar[0] = False

    return np.where(conservar[etiquetas], 255, 0).astype(np.uint8)


# -- estrategias de capa -------------------------------------------------


def _separar_por_color(imagen, opciones: OpcionesVectorizado, documento: Documento):
    """Agrupa los colores de la imagen y devuelve una máscara por grupo.

    Es la estrategia más fiable cuando el plano usa color para codificar
    información. En un dibujo a tinta negra dará una sola capa útil.
    """
    import cv2

    muestras = imagen.reshape(-1, 3).astype(np.float32)
    criterio = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, etiquetas, centros = cv2.kmeans(
        muestras, opciones.n_colores, None, criterio, 3, cv2.KMEANS_PP_CENTERS
    )

    etiquetas = etiquetas.reshape(imagen.shape[:2])
    centros = centros.astype(np.uint8)

    # El grupo más claro y más numeroso se toma por fondo del papel.
    luminancias = centros.astype(float) @ np.array([0.114, 0.587, 0.299])
    fondo = int(np.argmax(luminancias))

    capas: dict[str, np.ndarray] = {}
    for indice, centro in enumerate(centros):
        if indice == fondo:
            continue
        mascara = np.where(etiquetas == indice, 255, 0).astype(np.uint8)
        mascara = _quitar_motas(mascara, opciones.area_minima)
        if not mascara.any():
            continue

        b, g, r = (int(v) for v in centro)
        nombre = f"COLOR_{r:02X}{g:02X}{b:02X}"
        capas[nombre] = mascara
        documento.capas[nombre] = Capa(nombre=nombre, color=(r, g, b))

    documento.avisos.append(
        Aviso(
            "info",
            f"La imagen se ha agrupado en {len(capas)} colores además del fondo.",
        )
    )
    return capas


def _separar_por_grosor(binaria, opciones: OpcionesVectorizado, documento: Documento):
    """Reparte los trazos entre finos y gruesos.

    El grosor se mide con la transformada de distancia: en cada punto del trazo
    indica lo lejos que queda el borde más próximo, de modo que el doble de ese
    valor es el ancho de la línea.
    """
    import cv2

    distancia = cv2.distanceTransform(binaria, cv2.DIST_L2, 5)
    grosores = distancia[binaria > 0] * 2
    if grosores.size == 0:
        return {"IMAGEN": binaria}

    frontera = (
        opciones.umbral_grosor
        if opciones.umbral_grosor is not None
        else float(np.median(grosores))
    )

    finos = np.where((binaria > 0) & (distancia * 2 <= frontera), 255, 0).astype(np.uint8)
    gruesos = np.where((binaria > 0) & (distancia * 2 > frontera), 255, 0).astype(np.uint8)

    documento.avisos.append(
        Aviso(
            "info",
            f"Frontera entre trazo fino y grueso: {frontera:.1f} píxeles.",
            "La separación es gráfica, no de significado: no distingue un muro "
            "de una curva de nivel si están dibujados con el mismo grosor.",
        )
    )

    capas = {}
    if finos.any():
        capas["TRAZO_FINO"] = finos
        documento.capas["TRAZO_FINO"] = Capa(nombre="TRAZO_FINO", color=(0, 255, 255))
    if gruesos.any():
        capas["TRAZO_GRUESO"] = gruesos
        documento.capas["TRAZO_GRUESO"] = Capa(nombre="TRAZO_GRUESO", color=(255, 80, 80))
    return capas


# -- extracción de trazos ------------------------------------------------


def _trazos_de(
    binaria, opciones: OpcionesVectorizado
) -> tuple[list[list[Punto2D]], int]:
    """Convierte una máscara binaria en polilíneas siguiendo su esqueleto."""
    import cv2

    esqueleto = adelgazar(binaria)
    caminos = _fusionar(_seguir_caminos(esqueleto))

    polilineas: list[list[Punto2D]] = []
    descartados = 0

    for camino in caminos:
        if _longitud(camino) < opciones.longitud_minima:
            descartados += 1
            continue

        # Los caminos vienen en (fila, columna), que es como numpy recorre una
        # imagen; a partir de aquí se trabaja en (x, y). Confundirlos transpone
        # el dibujo entero sin que nada falle de forma visible.
        en_xy = np.array([(x, y) for y, x in camino], dtype=np.float32).reshape(-1, 1, 2)
        simplificado = cv2.approxPolyDP(en_xy, opciones.tolerancia, False)
        reducido = [(float(p[0][0]), float(p[0][1])) for p in simplificado]

        if len(reducido) >= 2:
            polilineas.append(reducido)
        else:
            descartados += 1

    return polilineas, descartados


#: Desplazamientos a los ocho vecinos de un píxel.
_VECINOS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))

#: Tope de iteraciones del adelgazado. Cada pasada quita como mucho una capa de
#: píxeles del contorno, así que un trazo de grosor razonable converge en pocas;
#: el límite solo protege de una imagen patológica.
_MAX_PASADAS_ADELGAZADO = 60


def adelgazar(binaria: np.ndarray) -> np.ndarray:
    """Reduce el trazo a un píxel de ancho por el método de Zhang-Suen.

    Se implementa aquí en lugar de usar el de los módulos adicionales de OpenCV
    porque esos módulos pesan más de 60 MB en el instalador y esta es la única
    función que se usaba de ellos. El algoritmo cabe en una pantalla y las
    pruebas comprueban lo que importa: que una línea gruesa dé un solo trazo y
    que una recta no se parta.

    Cada pasada marca los píxeles del borde que pueden retirarse sin romper la
    conectividad ni acortar los extremos, y se repite hasta que no queda
    ninguno.
    """
    img = (binaria > 0).astype(np.uint8)

    for _ in range(_MAX_PASADAS_ADELGAZADO):
        quitados = 0
        for paso in (0, 1):
            marcados = _marcar_sobrantes(img, paso)
            if marcados.any():
                img[marcados] = 0
                quitados += int(marcados.sum())
        if not quitados:
            break

    return (img * 255).astype(np.uint8)


def _marcar_sobrantes(img: np.ndarray, paso: int) -> np.ndarray:
    """Píxeles que pueden retirarse en esta media iteración."""
    p = np.pad(img, 1, mode="constant")

    # Vecinos en el orden del algoritmo: norte y luego en sentido horario.
    p2 = p[:-2, 1:-1]
    p3 = p[:-2, 2:]
    p4 = p[1:-1, 2:]
    p5 = p[2:, 2:]
    p6 = p[2:, 1:-1]
    p7 = p[2:, :-2]
    p8 = p[1:-1, :-2]
    p9 = p[:-2, :-2]

    vecinos = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9

    # Transiciones de 0 a 1 recorriendo el vecindario en círculo. Que haya
    # exactamente una garantiza que el píxel no une dos partes del trazo.
    secuencia = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
    transiciones = sum(
        ((a == 0) & (b == 1)).astype(np.uint8)
        for a, b in zip(secuencia, secuencia[1:])
    )

    if paso == 0:
        c1 = (p2 * p4 * p6) == 0
        c2 = (p4 * p6 * p8) == 0
    else:
        c1 = (p2 * p4 * p8) == 0
        c2 = (p2 * p6 * p8) == 0

    return (
        (img == 1)
        & (vecinos >= 2)
        & (vecinos <= 6)
        & (transiciones == 1)
        & c1
        & c2
    )


def _seguir_caminos(esqueleto) -> list[list[tuple[int, int]]]:
    """Recorre un esqueleto de un píxel de ancho y devuelve sus caminos.

    Se parte de los extremos y de los cruces, y se avanza hasta topar con otro.
    Lo que queda sin visitar después son lazos cerrados sin ningún cruce, que se
    recorren aparte: de otro modo, un círculo dibujado desaparecería.
    """
    puntos = np.argwhere(esqueleto > 0)
    if puntos.size == 0:
        return []

    ocupados = {(int(y), int(x)) for y, x in puntos}
    vecinos_de = {p: _vecinos_utiles(p, ocupados) for p in ocupados}

    # Un píxel con un solo vecino es un extremo; con tres o más, un cruce.
    especiales = [p for p, v in vecinos_de.items() if len(v) != 2]

    caminos: list[list[tuple[int, int]]] = []
    usados: set[frozenset] = set()

    for inicio in especiales:
        for siguiente in vecinos_de[inicio]:
            arista = frozenset((inicio, siguiente))
            if arista in usados:
                continue
            camino = _recorrer(inicio, siguiente, vecinos_de, usados)
            if len(camino) >= 2:
                caminos.append(camino)

    # Lazos cerrados: ningún píxel especial por el que empezar.
    visitados = {p for c in caminos for p in c}
    for punto in ocupados - visitados:
        if len(vecinos_de[punto]) != 2:
            continue
        camino = _recorrer(punto, vecinos_de[punto][0], vecinos_de, usados)
        if len(camino) >= 3:
            camino.append(camino[0])
            caminos.append(camino)
        visitados.update(camino)

    return caminos


def _fusionar(caminos: list[list[tuple[int, int]]]) -> list[list[tuple[int, int]]]:
    """Encadena los tramos que se continúan uno a otro.

    El adelgazamiento deja píxeles con tres vecinos donde el trazo cambia de
    ortogonal a diagonal, y esos falsos cruces parten una línea recta en decenas
    de trozos. Aquí se vuelven a unir los tramos que confluyen en un punto por
    el que solo pasan dos de ellos, que es un cambio de dirección y no una
    bifurcación real.
    """
    incidentes: dict[tuple[int, int], list[int]] = {}
    for indice, camino in enumerate(caminos):
        for extremo in (camino[0], camino[-1]):
            incidentes.setdefault(extremo, []).append(indice)

    vivos = {i: list(c) for i, c in enumerate(caminos)}
    fusionado = True

    while fusionado:
        fusionado = False
        for punto, indices in incidentes.items():
            presentes = [i for i in indices if i in vivos]
            if len(presentes) != 2:
                continue

            a, b = presentes
            if a == b:  # el mismo tramo cerrándose sobre sí mismo
                continue

            uno, otro = vivos[a], vivos[b]
            unido = _encadenar(uno, otro, punto)
            if unido is None:
                continue

            vivos[a] = unido
            del vivos[b]
            for extremo in (unido[0], unido[-1]):
                incidentes.setdefault(extremo, []).append(a)
            fusionado = True

    return list(vivos.values())


def _encadenar(uno, otro, punto):
    """Une dos tramos por el extremo que comparten, orientándolos."""
    if uno[-1] != punto:
        uno = uno[::-1]
    if otro[0] != punto:
        otro = otro[::-1]
    if uno[-1] != punto or otro[0] != punto:
        return None
    return uno + otro[1:]


def _recorrer(inicio, siguiente, vecinos_de, usados) -> list[tuple[int, int]]:
    """Avanza por el esqueleto hasta llegar a un extremo o a un cruce."""
    camino = [inicio, siguiente]
    usados.add(frozenset((inicio, siguiente)))

    anterior, actual = inicio, siguiente
    while len(vecinos_de[actual]) == 2:
        candidatos = [v for v in vecinos_de[actual] if v != anterior]
        if not candidatos:
            break
        proximo = candidatos[0]
        arista = frozenset((actual, proximo))
        if arista in usados:
            break
        usados.add(arista)
        camino.append(proximo)
        anterior, actual = actual, proximo

    return camino


def _adyacentes(punto):
    y, x = punto
    return [(y + dy, x + dx) for dy, dx in _VECINOS]


def _vecinos_utiles(punto, ocupados) -> list[tuple[int, int]]:
    """Vecinos de un píxel, descartando las diagonales redundantes.

    En una línea con escalones —cualquiera que no sea perfectamente recta— el
    píxel de la esquina toca a la vez al de al lado y al de la diagonal
    siguiente, y aparenta ser una bifurcación. Cada falso cruce parte el trazo,
    y una recta larga acaba troceada en cientos de fragmentos de dos píxeles.

    Si dos vecinos son adyacentes entre sí, la conexión diagonal sobra: se llega
    igual dando el rodeo ortogonal.
    """
    y, x = punto
    vecinos = [(y + dy, x + dx) for dy, dx in _VECINOS if (y + dy, x + dx) in ocupados]

    utiles = []
    for vecino in vecinos:
        dy, dx = vecino[0] - y, vecino[1] - x
        if dy and dx:  # diagonal
            ortogonales = ((y + dy, x), (y, x + dx))
            if any(o in ocupados for o in ortogonales):
                continue
        utiles.append(vecino)
    return utiles


def _longitud(camino) -> float:
    """Longitud de un camino dado en (fila, columna)."""
    total = 0.0
    for (y0, x0), (y1, x1) in zip(camino, camino[1:]):
        total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return total


def _a_dibujo(punto: Punto2D, alto: int, escala: float) -> Punto2D:
    """Lleva un punto de la imagen al sistema del modelo.

    Las filas de una imagen crecen hacia abajo y las ordenadas de un plano hacia
    arriba, de modo que el eje se voltea respecto a la altura de la imagen.
    """
    x, y = punto
    return (x * escala, (alto - y) * escala)


def calcular_escala(
    p1: Punto2D, p2: Punto2D, distancia_real: float
) -> float:
    """Unidades de dibujo por píxel, a partir de dos puntos de distancia conocida.

    Es la calibración: sin ella el dibujo sale en píxeles y no sirve para medir.
    En un plano publicado, lo natural es marcar los extremos de su escala
    gráfica.
    """
    separacion = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
    if separacion <= 0:
        raise VectorizacionError(
            "Los dos puntos de calibración no pueden ser el mismo."
        )
    return distancia_real / separacion
