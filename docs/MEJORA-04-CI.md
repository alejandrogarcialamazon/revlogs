# Mejora 4: validación automática en GitHub

Fecha: 06/11/2026. Publicación autorizada: 18:15 Buenos Aires.

## Implementación

`.github/workflows/ci.yml` ejecuta pruebas al publicar en main, abrir o actualizar
un pull request y por workflow_dispatch. Una matriz de Ubuntu prueba Python
3.10, 3.11, 3.12, 3.13 y 3.14, sin cancelar otras versiones cuando una falla.
Cada versión ejecuta unittest, compilación, construcción de wheel/sdist y prueba
el paquete instalado fuera del árbol fuente.

El job de calidad ejecuta Ruff (análisis y formato) y mypy estricto en Python 3.14.
Las dependencias opcionales dev están fijadas y no agregan dependencias de
ejecución al analizador. Ruff tiene reglas explícitas para resultados consistentes
entre la estación y CI. Los jobs tienen timeout y cancelan ejecuciones anteriores
de la misma referencia. Las acciones oficiales checkout y setup-python están
fijadas al SHA de sus versiones verificadas. El workflow solo necesita lectura
de contenido, no conserva credenciales de checkout ni publica paquetes/reportes.

`tools/check_distribution.py` instala el wheel sin red en un venv temporal,
comprueba CLI, código de umbral, conteos y repetición de reportes, y ejecuta
pip check. El entorno temporal se elimina. Requiere Linux y soporte venv/ensurepip,
disponibles en los runners hospedados; no modifica la instalación global.

## Reproducción local

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
.venv/bin/python -m ruff check revlogs tools tests
.venv/bin/python -m ruff format --check revlogs tools tests
.venv/bin/python -m mypy revlogs tools tests
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m build
.venv/bin/python tools/check_distribution.py dist
```

## Validación y límites

Resultados comprobados: actionlint sin errores, 50 pruebas locales y 50 remotas,
Ruff (análisis/formato), mypy estricto, compilación y construcción aprobados.
El smoke test instaló el wheel sin red y verificó CLI, conteos, umbrales, reportes
repetidos y pip check. La mejora 3 también pasó 50 pruebas desde clon limpio.
En el host remoto Python 3.10.12 se repitieron suite, compilación y CLI sobre
copia temporal eliminada al terminar, sin sudo ni trasladar credenciales.
Los jobs reales de GitHub y las versiones adicionales se ejecutarán al publicar
el commit de las 18:15: su resultado no se presume aprobado antes de ejecutarse.
El CI no despliega infraestructura, no hace push y no reemplaza los temporizadores
de publicación autorizados. Los resultados operativos se guardan fuera de Git.
