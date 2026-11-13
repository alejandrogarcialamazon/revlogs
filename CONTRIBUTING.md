# Contribuir a revlogs

Python >=3.10 y Linux; ejecución sin dependencias externas. Usar exclusivamente
logs sintéticos en incidencias, ejemplos y pruebas. No adjuntar reportes operativos.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m ruff check revlogs tools tests
.venv/bin/python -m ruff format --check revlogs tools tests
.venv/bin/python -m mypy revlogs tools tests
.venv/bin/python -m build
.venv/bin/python tools/check_distribution.py dist
```

Explicar el problema, el comportamiento final y las verificaciones en cada PR.
Agregar pruebas funcionales de regresión para cambios de comportamiento y un
archivo docs/MEJORA-NN-*.md. Mantener los límites de recursos y apertura segura.
Nuevos formatos de salida implementan ReportRenderer; patrones se agregan mediante
configuración, sin introducir dependencias de ejecución.
