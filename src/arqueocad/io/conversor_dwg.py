"""Conversión de DWG a DXF mediante un programa externo.

DWG es un formato propietario y cerrado, sin especificación pública. En lugar de
enlazar una biblioteca de lectura —lo que obligaría a ArqueoCAD a adoptar la
licencia GPL-3.0 de LibreDWG—, se invoca un conversor como proceso
independiente. Llamar a un programa por línea de órdenes es agregación y no obra
derivada, de modo que la licencia de ArqueoCAD no se ve afectada.

Se buscan dos conversores, por orden de calidad:

1. **ODA File Converter**, gratuito y oficial de la Open Design Alliance, con
   soporte completo de todas las versiones de DWG. No es redistribuible, así que
   se usa solo si el usuario lo tiene instalado.
2. **dwg2dxf**, de LibreDWG. Libre y acompañable, pero con soporte fiable solo
   hasta R2000 y parcial en las versiones posteriores, que son las que producen
   los AutoCAD actuales.

Cuando el conversor disponible no cubre con garantías la versión del archivo, se
avisa antes de abrirlo en lugar de entregar un plano incompleto con apariencia
correcta.
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
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..core.modelo import Aviso

#: Firma de los seis primeros bytes de un DWG y versión comercial que
#: representa. Permite avisar de las limitaciones antes de intentar la
#: conversión.
VERSIONES: dict[str, str] = {
    "AC1006": "R10",
    "AC1009": "R11/R12",
    "AC1012": "R13",
    "AC1014": "R14",
    "AC1015": "AutoCAD 2000",
    "AC1018": "AutoCAD 2004",
    "AC1021": "AutoCAD 2007",
    "AC1024": "AutoCAD 2010",
    "AC1027": "AutoCAD 2013",
    "AC1032": "AutoCAD 2018",
}

#: Versiones que LibreDWG lee con garantías. De AC1018 en adelante su soporte es
#: parcial y conviene decirlo.
FIABLES_EN_LIBREDWG = {"AC1006", "AC1009", "AC1012", "AC1014", "AC1015"}

#: Tiempo máximo de conversión. Un plano grande puede tardar, pero un conversor
#: que se queda esperando una ventana no debe bloquear la aplicación.
TIEMPO_MAXIMO = 180


class ConversionDWGError(Exception):
    """La conversión ha fallado."""


class SinConversor(Exception):
    """No se ha encontrado ningún conversor de DWG en el sistema."""


@dataclass(frozen=True)
class Conversor:
    """Un conversor localizado en el sistema."""

    nombre: str
    ruta: Path
    completo: bool

    @property
    def descripcion(self) -> str:
        alcance = "todas las versiones" if self.completo else "soporte parcial de las versiones recientes"
        return f"{self.nombre} ({alcance})"


def version_dwg(ruta: Path) -> tuple[str, str]:
    """Devuelve la firma del archivo y la versión comercial que representa."""
    try:
        with open(ruta, "rb") as archivo:
            firma = archivo.read(6).decode("ascii", errors="replace")
    except OSError as exc:
        raise ConversionDWGError(f"No se puede leer «{ruta.name}»: {exc}") from exc

    return firma, VERSIONES.get(firma, "desconocida")


def detectar() -> list[Conversor]:
    """Localiza los conversores disponibles, el mejor primero."""
    encontrados: list[Conversor] = []

    oda = _buscar_oda()
    if oda is not None:
        encontrados.append(Conversor("ODA File Converter", oda, completo=True))

    libredwg = _buscar_dwg2dxf()
    if libredwg is not None:
        encontrados.append(Conversor("dwg2dxf (LibreDWG)", libredwg, completo=False))

    return encontrados


def convertir(ruta: Path, carpeta_destino: Path | None = None) -> tuple[Path, list[Aviso]]:
    """Convierte un DWG a DXF y devuelve la ruta del resultado.

    El DXF se escribe en una carpeta temporal salvo que se indique otra. No se
    deja junto al original: el usuario no ha pedido un archivo nuevo en su
    carpeta de trabajo, solo abrir el plano.

    Raises:
        SinConversor: si no hay ningún conversor instalado.
        ConversionDWGError: si la conversión falla.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo: {ruta}")

    conversores = detectar()
    if not conversores:
        raise SinConversor(_mensaje_sin_conversor())

    conversor = conversores[0]
    avisos: list[Aviso] = []

    firma, version = version_dwg(ruta)
    avisos.append(
        Aviso(
            "info",
            f"«{ruta.name}» está en formato {version}; convertido con {conversor.nombre}.",
        )
    )

    if not conversor.completo and firma not in FIABLES_EN_LIBREDWG:
        avisos.append(
            Aviso(
                "aviso",
                f"LibreDWG solo cubre parcialmente el formato {version}.",
                "Puede faltar geometría o llegar alterada. Para una conversión "
                "completa conviene instalar ODA File Converter, que es gratuito, "
                "o exportar a DXF desde el propio AutoCAD.",
            )
        )

    if carpeta_destino is None:
        carpeta_destino = Path(tempfile.mkdtemp(prefix="arqueocad_"))
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    destino = carpeta_destino / f"{ruta.stem}.dxf"

    if conversor.nombre.startswith("ODA"):
        _convertir_con_oda(conversor.ruta, ruta, carpeta_destino, destino)
    else:
        _convertir_con_dwg2dxf(conversor.ruta, ruta, destino)

    if not destino.is_file() or destino.stat().st_size == 0:
        raise ConversionDWGError(
            f"{conversor.nombre} no ha producido ningún archivo a partir de "
            f"«{ruta.name}». El archivo puede estar dañado o usar una versión "
            "no admitida."
        )

    return destino, avisos


# -- localización --------------------------------------------------------


def _buscar_oda() -> Path | None:
    """Busca ODA File Converter en las rutas habituales de cada sistema."""
    en_path = shutil.which("ODAFileConverter")
    if en_path:
        return Path(en_path)

    sistema = platform.system()
    candidatos: list[Path] = []

    if sistema == "Windows":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if not base:
                continue
            raiz = Path(base) / "ODA"
            if raiz.is_dir():
                # El instalador crea una carpeta por versión, del tipo
                # «ODAFileConverter 25.4.0».
                candidatos.extend(sorted(raiz.glob("*/ODAFileConverter.exe"), reverse=True))
    elif sistema == "Darwin":
        candidatos.append(
            Path("/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter")
        )
    else:
        candidatos.extend(
            [
                Path("/usr/bin/ODAFileConverter"),
                Path("/usr/local/bin/ODAFileConverter"),
                Path("/opt/oda/ODAFileConverter"),
            ]
        )

    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    return None


def _buscar_dwg2dxf() -> Path | None:
    """Busca dwg2dxf, primero el acompañado y después el del sistema."""
    sufijo = ".exe" if platform.system() == "Windows" else ""
    carpeta = _carpeta_vendor() / f"dwg2dxf{sufijo}"
    if carpeta.is_file():
        return carpeta

    en_path = shutil.which("dwg2dxf")
    return Path(en_path) if en_path else None


def _carpeta_vendor() -> Path:
    """Carpeta donde se acompaña el binario de LibreDWG para esta plataforma."""
    sistemas = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}
    nombre = sistemas.get(platform.system(), "linux")
    return Path(__file__).resolve().parents[3] / "vendor" / "dwg2dxf" / nombre


# -- ejecución -----------------------------------------------------------


def _convertir_con_oda(
    programa: Path, origen: Path, carpeta_destino: Path, destino: Path
) -> None:
    """Ejecuta ODA File Converter, que trabaja sobre carpetas y no sobre archivos.

    Se aísla el archivo en una carpeta de entrada propia para que el conversor no
    procese de paso todos los planos que haya junto al original.
    """
    with tempfile.TemporaryDirectory(prefix="arqueocad_dwg_") as temporal:
        entrada = Path(temporal)
        shutil.copy2(origen, entrada / origen.name)

        orden = [
            str(programa),
            str(entrada),
            str(carpeta_destino),
            "ACAD2018",   # versión de salida
            "DXF",        # tipo de salida
            "0",          # sin recorrer subcarpetas
            "1",          # auditar y reparar
            "*.DWG",
        ]
        _ejecutar(orden, "ODA File Converter")

    # El conversor respeta el nombre base, pero no siempre las mayúsculas de la
    # extensión ni la caja del nombre.
    if not destino.is_file():
        for producido in carpeta_destino.glob("*.[dD][xX][fF]"):
            producido.rename(destino)
            break


def _convertir_con_dwg2dxf(programa: Path, origen: Path, destino: Path) -> None:
    _ejecutar(
        [str(programa), "-o", str(destino), str(origen)],
        "dwg2dxf",
    )


#: Variables que PyInstaller inyecta para que el ejecutable empaquetado
#: encuentre sus propias bibliotecas. Un subproceso que también use Qt las
#: heredaría y cargaría las bibliotecas de ArqueoCAD en lugar de las suyas.
_VARIABLES_INYECTADAS = (
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "QT_QPA_PLATFORM",
    "QT_QPA_FONTDIR",
    "QML2_IMPORT_PATH",
    "QML_IMPORT_PATH",
    "QT_SCALE_FACTOR",
    "QT_SCREEN_SCALE_FACTORS",
)


def _entorno_limpio() -> dict[str, str]:
    """Entorno para el subproceso, sin rastro del empaquetado.

    ODA File Converter es a su vez una aplicación Qt. Ejecutado desde el
    ArqueoCAD empaquetado, hereda las rutas de Qt que PyInstaller inyecta y
    carga bibliotecas de otra versión, con lo que se estrella antes de convertir
    nada. Desde el intérprete de desarrollo el problema no aparece, de modo que
    solo se manifiesta en el programa ya distribuido.
    """
    entorno = dict(os.environ)

    for variable in _VARIABLES_INYECTADAS:
        entorno.pop(variable, None)

    # PyInstaller conserva los valores originales con el sufijo «_ORIG» cuando
    # los sustituye; si están, se restauran.
    for variable in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "PATH"):
        original = entorno.pop(f"{variable}_ORIG", None)
        if original is not None:
            entorno[variable] = original
        elif variable != "PATH":
            entorno.pop(variable, None)

    # La carpeta del paquete se retira del PATH para que el conversor no
    # encuentre ahí las DLL de Qt de ArqueoCAD.
    carpeta = getattr(sys, "_MEIPASS", None)
    if carpeta and entorno.get("PATH"):
        partes = [
            p for p in entorno["PATH"].split(os.pathsep)
            if p and not p.startswith(str(carpeta))
        ]
        entorno["PATH"] = os.pathsep.join(partes)

    return entorno


def _ejecutar(orden: list[str], nombre: str) -> None:
    """Lanza el conversor sin dejar que abra ventanas ni se quede colgado."""
    opciones: dict = {"env": _entorno_limpio()}
    if platform.system() == "Windows":
        # ODA File Converter es una aplicación gráfica aunque se use en modo
        # de lotes; sin esto aparecería una ventana en mitad del trabajo.
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        opciones["startupinfo"] = info
        opciones["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        resultado = subprocess.run(
            orden,
            capture_output=True,
            text=True,
            timeout=TIEMPO_MAXIMO,
            check=False,
            **opciones,
        )
    except FileNotFoundError as exc:
        raise ConversionDWGError(f"No se puede ejecutar {nombre}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionDWGError(
            f"{nombre} ha superado los {TIEMPO_MAXIMO} segundos y se ha interrumpido."
        ) from exc

    # Algunos conversores devuelven un código distinto de cero pese a haber
    # escrito el archivo, de modo que el código por sí solo no basta para
    # decidir; quien llama comprueba después que exista la salida.
    if resultado.returncode != 0 and not (resultado.stdout or resultado.stderr):
        raise ConversionDWGError(
            f"{nombre} ha terminado con el código {resultado.returncode} sin dar detalles."
        )


def _mensaje_sin_conversor() -> str:
    return (
        "Para abrir archivos DWG hace falta un conversor externo, porque DWG es "
        "un formato propietario y cerrado.\n\n"
        "La opción recomendada es ODA File Converter, gratuito y con soporte "
        "completo:\n"
        "https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
        "Una vez instalado, ArqueoCAD lo detecta solo.\n\n"
        "Como alternativa, el DWG puede exportarse a DXF desde el propio AutoCAD "
        "o desde BricsCAD."
    )
