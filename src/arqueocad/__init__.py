"""ArqueoCAD — lectura de planos DWG, DXF y SVG y separación por capas.

Pensada para el trabajo con planimetría de excavación: abrir un plano, revisar
sus capas y obtener cada una en su propio archivo DXF o SVG sin alterar la
geometría ni la escala.
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

__version__ = "0.2.0"
__all__ = ["__version__"]
