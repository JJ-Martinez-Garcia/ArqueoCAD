# ArqueoCAD

Aplicación de escritorio para leer planos **DWG**, **DXF** y **SVG** y obtener
cada capa en su propio archivo, sin alterar la geometría ni la escala. Pensada
para planimetría de excavación.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Modelo interno, lectura de DXF, visor y panel de capas | **terminada** |
| 2 | Separación por capas y exportación a DXF y SVG | **terminada** |
| 3 | Lectura de SVG | **terminada** |
| 4 | Entrada DWG mediante conversor externo | **terminada** |
| 5 | Proceso por lotes, medición, empaquetado y distribución | **terminada** |

## Puesta en marcha

Requiere Python 3.12. Desde la carpeta del proyecto:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para ejecutar la aplicación:

```bash
.venv\Scripts\python.exe -m arqueocad.app
```

Admite abrir un plano desde la línea de órdenes, y también arrastrarlo sobre la
ventana.

## Pruebas

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

Las pruebas se apoyan en `tests/plano_de_prueba.py`, que genera un DXF sintético
con los tipos de entidad que más problemas dan en una conversión: polilíneas con
tramos curvos, splines, elipses, sombreados, sólidos de cuatro vértices,
acotación y bloques con geometría repartida entre la capa «0» y una capa propia.

### Herramientas de línea de órdenes

```bash
.venv\Scripts\python.exe tools/analizar.py plano.dxf
.venv\Scripts\python.exe tools/separar.py plano.dxf carpeta_salida --svg
.venv\Scripts\python.exe tools/verificar_separacion.py plano.dxf carpeta_salida
```

`verificar_separacion` vuelve a leer cada archivo generado y contrasta el
recuento de entidades y la envolvente contra el original. Es la comprobación que
detecta una exportación que «funciona» pero entrega geometría desplazada.

Para comprobar que la interfaz monta y pinta:

```bash
.venv\Scripts\python.exe tools/captura_prueba.py
```

Guarda una captura en `tests/captura.png`. Conviene ejecutarlo con el motor
gráfico real (`QT_QPA_PLATFORM=windows`), porque el modo sin pantalla carece de
fuentes y dibuja todos los textos como cuadros vacíos.

## Cómo está organizado

```
src/arqueocad/
├─ core/       modelo interno neutro, geometría, unidades
│  ├─ modelo.py      Documento, Capa y las primitivas de dibujo
│  ├─ geometria.py   envolventes y aplanado de curvas
│  └─ unidades.py    unidades de dibujo y conversiones de escala
├─ io/         lectores y escritores
│  ├─ lector.py      elige el lector según la extensión
│  ├─ lector_dxf.py  DXF → modelo interno
│  ├─ lector_svg.py  SVG → modelo interno
│  ├─ escritor_dxf.py  copia fiel de las entidades originales
│  └─ escritor_svg.py  capas de Inkscape y medidas reales
├─ ui/         interfaz (PySide6)
│  ├─ vista_plano.py  lienzo con desplazamiento y zoom
│  ├─ panel_capas.py  lista de capas, filtro y selección
│  └─ ventana.py      ventana principal
└─ app.py      punto de entrada
```

Todo lo que entra se traduce al **modelo interno neutro** y todo lo que sale se
genera desde él. Así el número de conversores crece de forma lineal con los
formatos admitidos y no de forma cuadrática.

### Las seis conversiones posibles

| Entrada → Salida | DXF | SVG |
|---|---|---|
| **DXF** | copia fiel de las entidades originales | desde la geometría aplanada |
| **DWG** | ídem, tras convertir a DXF | ídem |
| **SVG** | desde la geometría del modelo | desde la geometría del modelo |

La casilla SVG → DXF es la única que no puede copiar entidades de un documento
de origen, porque no lo hay. Se construye entonces con entidades nativas
—polilíneas, puntos, textos y sombreados— a partir del modelo interno, y se
avisa. No hay pérdida añadida: en un SVG la geometría ya venía en segmentos
rectos.

### Dos representaciones que conviven

- Las **primitivas aplanadas** sirven para dibujar en pantalla y para exportar a
  SVG. Las curvas ya vienen convertidas en segmentos rectos.
- El **documento de origen** se conserva intacto. La exportación a DXF copiará
  de él las entidades originales, de modo que splines, sombreados y bloques
  lleguen sin pérdida al archivo de salida.

## Criterios de diseño

**Nada se pierde en silencio.** Toda simplificación queda registrada como aviso
consultable desde *Ayuda › Avisos del archivo*: patrones de sombreado que no
tienen equivalente, fuentes sustituidas, presentaciones no cargadas, bloques que
superan el límite de anidamiento. Un plano que llega a la publicación con la
escala alterada es un error grave y difícil de detectar a simple vista.

**Una entidad defectuosa no invalida el archivo.** Cada conversión se aísla, y
lo que falla se anota en lugar de interrumpir la lectura. Los DXF procedentes de
conversión desde DWG traen con frecuencia entidades marginales.

**Visibilidad y exportación son cosas distintas.** En el panel de capas, la
casilla controla lo que se ve y la selección de filas lo que se exporta. Se
puede mantener a la vista una capa de referencia sin incluirla en la salida.

**Las capas auxiliares quedan fuera.** «Defpoints», donde AutoCAD guarda los
puntos de definición de las cotas, y cualquier capa marcada como no imprimible
se excluyen de la exportación por defecto.

**El blanco se convierte en negro al exportar a SVG.** El color 7 de AutoCAD se
dibuja blanco sobre el fondo negro del programa, pero se imprime negro sobre
papel. Sin esa conversión, el marco del cajetín y buena parte de la rotulación
desaparecen al abrir el archivo en Inkscape.

**Una capa apagada en el original sí se exporta.** Que estuviera congelada es un
estado de trabajo del dibujante, no una instrucción sobre la exportación: si el
usuario la selecciona, la quiere en el resultado.

## Cómo se separa un plano

Tres modos, combinables con los dos formatos de salida:

- **Un archivo por capa** — `plano_MURO_ADOBE_2024.dxf`, `plano_SARCÓFAGO_2024.dxf`…
- **Un solo archivo filtrado** — conserva la estructura con las capas elegidas.
- **Por grupos de capas** — disponible en el motor; la interfaz para definirlos
  llega en la fase 5.

Los nombres de capa conservan acentos y espacios, porque los tres sistemas los
admiten. Solo se sustituyen los caracteres que el sistema de archivos prohíbe.
No se despojan las tildes: en un mismo plano coexisten `PERIMETRO_TUMBA_2024` y
`PERÍMETRO_EXCAVADO_2024`, y ese saneo fundiría dos capas en un archivo.

## Lectura de SVG

Tres asuntos, ninguno evidente:

- **El eje Y va al revés.** En SVG crece hacia abajo y en CAD hacia arriba. La
  conversión lo voltea respecto a la altura del documento.
- **Las capas no son grupos.** Solo cuenta como capa un grupo con
  `inkscape:groupmode="layer"`. Un archivo sin capas declaradas se carga en una
  sola, y se avisa.
- **La escala ya viene resuelta.** `svgelements` aplica la transformación del
  `viewBox` y entrega píxeles CSS, de modo que pasar a milímetros es la
  constante de 96 ppp. Si el archivo no declara medidas físicas, no hay escala
  real que recuperar y se dice en lugar de suponer una.

La tolerancia de aplanado tiene un suelo relativo al tamaño del dibujo. Una
tolerancia absoluta obliga a partir cada círculo en cientos de tramos cuando el
plano mide decenas de metros: en un plano de excavación de 57 × 71 m con 549
entidades, la lectura pasaba de 30 segundos a 0,2 sin diferencia visible.

### Bloques

Un bloque insertado en una capa puede contener geometría dibujada en otras. Al
copiarlo entero —el comportamiento por defecto, que es el fiel—, esas capas
aparecen en el archivo de salida aunque no se hubieran pedido, y la exportación
lo advierte nombrándolas. Con la opción de **desplegar bloques**, la geometría se
reparte entre sus capas reales y el archivo lleva solo lo pedido, a costa de que
los bloques dejen de existir como tales.

## Entrada DWG

DWG es un formato propietario y cerrado, sin especificación pública. En lugar de
enlazar una biblioteca de lectura —lo que obligaría a ArqueoCAD a adoptar la
licencia GPL-3.0 de LibreDWG—, se invoca un conversor como proceso
independiente. Llamar a un programa por línea de órdenes es agregación y no obra
derivada, de modo que la licencia de ArqueoCAD no se ve afectada.

Se buscan dos, por orden de calidad:

| Conversor | Alcance | Distribución |
|---|---|---|
| ODA File Converter | Todas las versiones de DWG | Gratuito, lo instala el usuario |
| `dwg2dxf` (LibreDWG) | Fiable hasta R2000, parcial en adelante | Libre, acompañable en `vendor/` |

Si el conversor disponible no cubre con garantías la versión del archivo, se
avisa **antes** de abrirlo, en lugar de entregar un plano incompleto con
apariencia correcta. La versión se identifica por la firma de los seis primeros
bytes: `AC1015` es AutoCAD 2000, `AC1024` es 2010, `AC1032` es 2018.

`Ayuda › Conversores de DWG` informa de cuál se está usando. Las pruebas que
necesitan un conversor se saltan solas si no lo hay.

Verificado con ODA File Converter 27.1.0 sobre un plano de excavación en formato
AutoCAD 2010: el resultado leído desde el DWG es **idéntico al leído desde su DXF
equivalente** —549 entidades, 17 capas con contenido, mismos tipos y recuentos,
desplazamiento nulo en todas las capas—. Puede repetirse con cualquier pareja de
planos:

```bash
.venv\Scripts\python.exe tools/comparar.py plano.dwg plano.dxf
```

## Proceso por lotes

`Archivo › Separar por lotes` (Ctrl+L) aplica el mismo criterio a todos los
planos de una campaña. El filtro de capas admite comodines y varios patrones
separados por comas —`UE-*`, `*_2024`, `MURO*, SARCÓFAGO*`—, porque en un lote no
se sabe qué capas trae cada archivo pero sí qué familias interesan.

Un plano defectuoso no interrumpe la campaña: se anota el error y se sigue con
el resto. Con veinte planos, eso es la diferencia entre perder el trabajo y
perder un archivo.

## Medición

La tecla `M` activa la medición. Se marcan puntos con el botón izquierdo; el
derecho retira el último, `Esc` limpia y el botón central desplaza el plano. La
barra de estado da longitud, acimut y, a partir de tres puntos, área y
perímetro.

El acimut sigue la convención topográfica —0° al norte, creciendo hacia el
este—, que es la que interesa para orientar un muro. Si el plano no declara sus
unidades, las medidas se dan en unidades de dibujo y así se indica: presentar
«12,4 m» sobre un plano de escala desconocida sería inventar un dato.

## Empaquetado

```bash
.venv\Scripts\python.exe tools/crear_icono.py
.venv\Scripts\python.exe -m PyInstaller packaging/arqueocad.spec --noconfirm
dist\ArqueoCAD\ArqueoCAD.exe --comprobar
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\instalador.iss
```

Inno Setup instalado con `winget` va a `%LOCALAPPDATA%\Programs\Inno Setup 6\`,
no a `Program Files`, porque se instala en modo usuario.

Resultado: `dist\ArqueoCAD-0.1.0-windows-x64.exe` (36 MB) y, si se quiere la
versión portable, un ZIP de la carpeta `dist\ArqueoCAD` (50 MB).

`--comprobar` monta la aplicación entera, carga un plano si se le indica y sale
con código 0. Es imprescindible: con `console=False`, un ejecutable que falla al
arrancar muestra el error en un cuadro de diálogo y el proceso **sigue vivo**,
de modo que comprobar si el programa «sigue en marcha» da un falso correcto.

Dos trampas del empaquetado, ambas encontradas a base de que el ejecutable no
arrancara:

- **`unittest` no puede excluirse.** `pyparsing.testing` lo importa al cargarse,
  y ezdxf depende de pyparsing. Sin él, el paquete se construye limpiamente y
  luego no arranca.
- **El subproceso necesita un entorno limpio.** ODA File Converter es a su vez
  una aplicación Qt; si hereda las rutas de Qt que PyInstaller inyecta, carga
  bibliotecas de otra versión y se estrella. Desde el intérprete de desarrollo
  el problema no se ve, así que solo aparece en el programa ya distribuido.

`.github/workflows/construir.yml` produce los tres instaladores al publicar una
etiqueta `v*`, y comprueba en cada sistema que el ejecutable arranca antes de
empaquetarlo.

## Licencias

ArqueoCAD se distribuye bajo la **GPL-3.0**. El programa es libre: puede usarse,
copiarse, estudiarse y modificarse sin permiso. Quien distribuya una versión
modificada debe publicar también su código fuente bajo la misma licencia.

| Componente | Licencia |
|---|---|
| `ezdxf` | MIT |
| `svgelements` | MIT |
| `pyparsing` | MIT |
| `fonttools` | MIT |
| NumPy | BSD-3 |
| PySide6 / Qt 6 | LGPL-3.0 |

Todas son compatibles con la GPL-3.0. Se descartó PyQt, que obliga a licencia
comercial de pago para uso cerrado.

Los textos completos están en `licencias/`, que se genera con:

```bash
.venv\Scripts\python.exe tools/reunir_licencias.py
```

Los textos **se copian** de los paquetes instalados y de las copias verbatim que
distribuye el proyecto GNU, nunca se transcriben: un texto legal alterado es peor
que ninguno. El aviso de licencia de cada archivo fuente lo pone
`tools/poner_cabeceras.py`, que con `--comprobar` avisa si falta en alguno.

### Qué exige cada licencia

- **MIT y BSD** (ezdxf, svgelements, pyparsing, fonttools, NumPy): incluir su
  aviso de copyright y su texto completo en toda copia distribuida. Un listado
  de nombres no basta.
- **LGPL-3.0** (Qt/PySide6): incluir su texto y el de la GPL-3.0 en que se
  apoya, declarar su uso, indicar dónde obtener el fuente de Qt, y permitir que
  el usuario sustituya la biblioteca. Esto último se cumple porque el empaquetado
  deja las bibliotecas como archivos independientes; con un ejecutable único
  habría sido bastante más complicado.

El soporte DWG se resuelve invocando un conversor externo en lugar de enlazar
LibreDWG. Con ArqueoCAD ya bajo GPL-3.0 esa restricción desaparece, de modo que
integrar LibreDWG pasa a ser posible si algún día interesa evitar que el usuario
tenga que instalar ODA File Converter.

## Pendientes de decisión

- Certificado de firma de código para Windows, sin el cual SmartScreen advierte
  de «editor desconocido» al descargar el instalador.
- Notarización de macOS, sin la cual Gatekeeper bloquea la primera apertura.
