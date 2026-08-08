"""Escritura de DXF por copia de las entidades originales.

La geometría **no se reconstruye** a partir de las primitivas aplanadas del
visor: se copian las entidades tal como venían en el archivo de partida,
mediante el importador de ezdxf, que arrastra consigo los recursos de los que
dependen —capas, tipos de línea, estilos de texto y definiciones de bloque—.

Así, un spline sigue siendo un spline en el archivo de salida, y un sombreado
conserva su patrón. Aplanarlos para volver a escribirlos degradaría el dibujo de
forma irreversible.
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

import io
from pathlib import Path
from typing import Iterable

import ezdxf
from ezdxf.addons import Importer
from ezdxf.document import Drawing

from ..core.modelo import Aviso, Documento, Polilinea, Relleno, Texto
from ..core.modelo import Punto as PuntoEntidad

#: Tope de pasadas al desplegar bloques anidados, por si una definición
#: mal formada se refiere a sí misma.
MAXIMO_PASADAS_EXPLOSION = 8


class EscrituraDXFError(Exception):
    """El archivo de salida no ha podido generarse."""


def escribir_dxf(
    documento: Documento,
    capas: Iterable[str],
    destino: str | Path,
    explotar_bloques: bool = False,
    version: str | None = None,
) -> list[Aviso]:
    """Escribe un DXF con la geometría de las capas indicadas.

    Args:
        documento: plano de partida, que debe conservar su documento de origen.
        capas: nombres de las capas que se incluyen.
        destino: archivo a crear.
        explotar_bloques: si se despliegan las referencias de bloque antes de
            filtrar. Sin desplegar, un bloque insertado en una capa viaja
            entero con esa capa, aunque su interior pertenezca a otras.
        version: versión de DXF de salida; por defecto, la del original.

    Returns:
        Avisos de lo que se ha simplificado o quedado fuera.
    """
    seleccion = set(capas)
    if not seleccion:
        raise EscrituraDXFError("No se ha seleccionado ninguna capa.")

    avisos: list[Aviso] = []

    origen = documento.origen_ezdxf
    if origen is None:
        # Un plano leído de SVG no tiene documento de ezdxf del que copiar. Se
        # construye entonces desde las primitivas del modelo, que es exactamente
        # lo que el SVG contenía: allí la geometría ya venía en segmentos
        # rectos, de modo que no se pierde nada por el camino.
        return _escribir_desde_modelo(documento, seleccion, destino, version, avisos)

    if explotar_bloques:
        origen = _copia_con_bloques_desplegados(origen, avisos)

    salida = ezdxf.new(dxfversion=version or origen.dxfversion, setup=False)
    _copiar_cabecera(origen, salida)

    entidades = [
        entidad
        for entidad in origen.modelspace()
        if str(entidad.dxf.get("layer", "0")) in seleccion
    ]

    if not entidades:
        avisos.append(
            Aviso(
                "aviso",
                "Las capas seleccionadas no contienen ninguna entidad.",
                "El archivo se ha creado vacío.",
            )
        )

    importador = Importer(origen, salida)
    try:
        importador.import_entities(entidades, salida.modelspace())
        # `finalize` arrastra los recursos de los que dependen las entidades:
        # tablas de capas, tipos de línea, estilos de texto y bloques.
        importador.finalize()
    except Exception as exc:  # noqa: BLE001
        raise EscrituraDXFError(f"Error al copiar las entidades: {exc}") from exc

    _avisar_de_capas_arrastradas(origen, entidades, seleccion, avisos)

    # Una capa seleccionada pero vacía debe existir igualmente en la salida:
    # su ausencia haría creer que no formaba parte del plano.
    for nombre in sorted(seleccion):
        if nombre not in salida.layers:
            capa = documento.capas.get(nombre)
            salida.layers.add(
                name=nombre, color=capa.aci if capa else 7
            )

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        salida.saveas(destino)
    except IOError as exc:
        raise EscrituraDXFError(f"No se puede escribir «{destino.name}»: {exc}") from exc

    return avisos


def _escribir_desde_modelo(
    documento: Documento,
    seleccion: set[str],
    destino: str | Path,
    version: str | None,
    avisos: list[Aviso],
) -> list[Aviso]:
    """Construye un DXF a partir de las primitivas del modelo interno.

    Es la vía para los planos que no proceden de un DXF —hoy, los leídos de
    SVG—. La geometría se escribe con entidades nativas: polilíneas, puntos,
    textos y sombreados, cada uno en su capa.
    """
    salida = ezdxf.new(dxfversion=version or "R2018", setup=True)
    salida.header["$INSUNITS"] = int(documento.unidad)
    espacio = salida.modelspace()

    for nombre in sorted(seleccion):
        if nombre in salida.layers:
            continue
        capa = documento.capas.get(nombre)
        capa_ez = salida.layers.add(name=nombre)
        if capa is not None:
            capa_ez.rgb = capa.color

    escritas = 0
    for entidad in documento.entidades:
        if entidad.capa not in seleccion:
            continue
        atributos: dict = {"layer": entidad.capa}
        if entidad.color is not None:
            atributos["true_color"] = ezdxf.colors.rgb2int(entidad.color)

        if isinstance(entidad, Polilinea):
            if len(entidad.puntos) < 2:
                continue
            espacio.add_lwpolyline(
                entidad.puntos, close=entidad.cerrada, dxfattribs=atributos
            )
        elif isinstance(entidad, PuntoEntidad):
            espacio.add_point(entidad.posicion, dxfattribs=atributos)
        elif isinstance(entidad, Texto):
            _escribir_texto(espacio, entidad, atributos)
        elif isinstance(entidad, Relleno):
            _escribir_relleno(espacio, entidad, atributos)
        else:
            continue
        escritas += 1

    if not escritas:
        avisos.append(
            Aviso(
                "aviso",
                "Las capas seleccionadas no contienen ninguna entidad.",
                "El archivo se ha creado vacío.",
            )
        )

    avisos.append(
        Aviso(
            "info",
            "El DXF se ha generado a partir de la geometría del plano, no copiando "
            "entidades de un DXF de origen.",
            "Las curvas quedan como polilíneas, que es como ya venían en el archivo "
            "de partida.",
        )
    )

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        salida.saveas(destino)
    except IOError as exc:
        raise EscrituraDXFError(f"No se puede escribir «{destino.name}»: {exc}") from exc

    return avisos


def _escribir_texto(espacio, entidad: Texto, atributos: dict) -> None:
    """Escribe un rótulo, usando MTEXT solo cuando hay varias líneas."""
    if entidad.multilinea:
        texto = espacio.add_mtext(
            entidad.contenido,
            dxfattribs={**atributos, "char_height": entidad.altura},
        )
        texto.set_location(entidad.posicion, rotation=entidad.rotacion)
        return

    espacio.add_text(
        entidad.contenido,
        dxfattribs={
            **atributos,
            "height": entidad.altura,
            "rotation": entidad.rotacion,
        },
    ).set_placement(entidad.posicion)


def _escribir_relleno(espacio, entidad: Relleno, atributos: dict) -> None:
    """Escribe un sombreado sólido, o su contorno si no lo era."""
    contornos = [c for c in entidad.contornos if len(c) >= 3]
    if not contornos:
        return

    if not entidad.solido:
        for contorno in contornos:
            espacio.add_lwpolyline(contorno, close=True, dxfattribs=atributos)
        return

    sombreado = espacio.add_hatch(dxfattribs=atributos)
    for contorno in contornos:
        sombreado.paths.add_polyline_path(contorno, is_closed=True)


def _copiar_cabecera(origen: Drawing, salida: Drawing) -> None:
    """Traslada las variables de cabecera que afectan a la interpretación.

    Las unidades son la más importante: sin ellas, el archivo de salida quedaría
    sin escala declarada aunque el original sí la tuviera.
    """
    for variable in ("$INSUNITS", "$MEASUREMENT", "$AUNITS", "$LUNITS", "$PDMODE", "$PDSIZE"):
        try:
            valor = origen.header.get(variable)
        except Exception:  # noqa: BLE001
            continue
        if valor is not None:
            try:
                salida.header[variable] = valor
            except Exception:  # noqa: BLE001
                continue


def _avisar_de_capas_arrastradas(
    origen: Drawing,
    entidades: list,
    seleccion: set[str],
    avisos: list[Aviso],
) -> None:
    """Advierte de las capas que entran de rebote dentro de los bloques.

    Un bloque insertado en una capa puede contener geometría dibujada en otras.
    Al copiarlo entero, esas capas aparecen en el archivo de salida aunque no se
    hubieran pedido. No es un error —es cómo funciona el formato—, pero quien
    esperaba un archivo con una sola capa debe saberlo.
    """
    arrastradas: set[str] = set()

    def recorrer(nombre_bloque: str, profundidad: int) -> None:
        if profundidad >= MAXIMO_PASADAS_EXPLOSION:
            return
        try:
            bloque = origen.blocks[nombre_bloque]
        except KeyError:
            return
        for entidad in bloque:
            capa = str(entidad.dxf.get("layer", "0"))
            # La capa «0» no cuenta: dentro de un bloque significa «la del
            # lugar donde se inserte», no una capa propia.
            if capa != "0" and capa not in seleccion:
                arrastradas.add(capa)
            if entidad.dxftype() == "INSERT":
                recorrer(str(entidad.dxf.name), profundidad + 1)

    for entidad in entidades:
        if entidad.dxftype() == "INSERT":
            recorrer(str(entidad.dxf.name), 0)

    if arrastradas:
        avisos.append(
            Aviso(
                "aviso",
                f"{len(arrastradas)} capas aparecen en el archivo por venir dentro de bloques insertados.",
                "Son " + ", ".join(sorted(arrastradas))
                + ". Para repartir de verdad la geometría por capas, active la opción de desplegar bloques.",
            )
        )


def _copia_con_bloques_desplegados(origen: Drawing, avisos: list[Aviso]) -> Drawing:
    """Devuelve una copia del documento con las inserciones ya desplegadas.

    Se trabaja sobre una copia para no alterar el plano que el usuario tiene
    abierto. La copia se obtiene serializando el documento en memoria, que es la
    vía que garantiza independencia real entre ambos.
    """
    flujo = io.StringIO()
    origen.write(flujo)
    flujo.seek(0)
    copia = ezdxf.read(flujo)

    espacio = copia.modelspace()
    desplegadas = 0

    for pasada in range(MAXIMO_PASADAS_EXPLOSION):
        inserciones = list(espacio.query("INSERT"))
        if not inserciones:
            break

        for insercion in inserciones:
            capa_insercion = str(insercion.dxf.get("layer", "0"))
            try:
                hijas = list(insercion.virtual_entities())
            except Exception:  # noqa: BLE001
                continue

            for hija in hijas:
                # La geometría dibujada en la capa «0» dentro de un bloque
                # adopta la capa donde se inserta: así lo define el formato y es
                # lo que hace que un bloque tome el aspecto de su destino.
                if str(hija.dxf.get("layer", "0")) == "0":
                    hija.dxf.layer = capa_insercion
                espacio.add_entity(hija)

            espacio.delete_entity(insercion)
            desplegadas += 1
    else:
        if list(espacio.query("INSERT")):
            avisos.append(
                Aviso(
                    "aviso",
                    "Quedan bloques sin desplegar tras el límite de pasadas.",
                    "Puede haber una definición de bloque que se refiera a sí misma.",
                )
            )

    if desplegadas:
        avisos.append(
            Aviso(
                "info",
                f"Se han desplegado {desplegadas} inserciones de bloque para repartir su geometría entre las capas reales.",
                "Los bloques dejan de existir como tales en el archivo de salida.",
            )
        )

    return copia
