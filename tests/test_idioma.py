"""Pruebas del cambio de idioma."""

from __future__ import annotations

import pytest

from arqueocad.core.idioma import (
    CATALOGO,
    IDIOMA_POR_DEFECTO,
    IDIOMAS,
    detectar_del_sistema,
    fijar_idioma,
    idioma_actual,
    t,
)
from arqueocad.core.medicion import Medicion
from arqueocad.core.unidades import Unidad


@pytest.fixture(autouse=True)
def restaurar_idioma():
    """Cada prueba deja el idioma como estaba."""
    anterior = idioma_actual()
    yield
    fijar_idioma(anterior)


def test_el_idioma_por_defecto_es_el_espanol() -> None:
    assert IDIOMA_POR_DEFECTO == "es"
    assert set(IDIOMAS) == {"es", "en"}


def test_en_espanol_el_texto_no_se_toca() -> None:
    fijar_idioma("es")
    assert t("Separar por capas") == "Separar por capas"


def test_traduce_al_ingles() -> None:
    fijar_idioma("en")
    assert t("Separar por capas") == "Separate by layers"
    assert t("Capas") == "Layers"


def test_lo_no_traducido_sale_en_espanol() -> None:
    """Una frase sin traducir deja la interfaz utilizable; una clave suelta no."""
    fijar_idioma("en")
    inventado = "Un texto que no está en el catálogo"
    assert t(inventado) == inventado


def test_un_idioma_desconocido_cae_en_el_por_defecto() -> None:
    fijar_idioma("fr")
    assert idioma_actual() == IDIOMA_POR_DEFECTO


def test_las_plantillas_conservan_sus_huecos() -> None:
    """Si una traducción pierde un hueco, el formateo falla al ejecutarse.

    Es el fallo más fácil de colar al traducir y el más molesto de detectar,
    porque solo aparece cuando el usuario abre esa ventana concreta.
    """
    import re

    for original, traducido in CATALOGO.items():
        huecos_es = set(re.findall(r"\{(\w+)\}", original))
        huecos_en = set(re.findall(r"\{(\w+)\}", traducido))
        assert huecos_es == huecos_en, (
            f"los huecos no coinciden en «{original[:50]}»: "
            f"{huecos_es} frente a {huecos_en}"
        )


def test_el_catalogo_no_tiene_traducciones_vacias() -> None:
    for original, traducido in CATALOGO.items():
        assert traducido.strip(), f"traducción vacía para «{original[:50]}»"


def test_detecta_el_idioma_del_sistema() -> None:
    assert detectar_del_sistema() in IDIOMAS


def test_la_medicion_se_traduce() -> None:
    medicion = Medicion(unidad=Unidad.METROS)
    fijar_idioma("en")
    assert "first point" in medicion.resumen()

    medicion.anadir((0.0, 0.0))
    medicion.anadir((3.0, 4.0))
    assert "Length" in medicion.resumen()

    fijar_idioma("es")
    assert "Longitud" in medicion.resumen()


def test_las_unidades_se_traducen() -> None:
    from arqueocad.core.unidades import nombre as nombre_unidad

    fijar_idioma("en")
    assert t(nombre_unidad(Unidad.METROS)) == "metres"
    assert t(nombre_unidad(Unidad.SIN_DEFINIR)) == "undefined"
