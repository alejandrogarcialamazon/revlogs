# Parser TOML para Python 3.10

Se incluye tomli 2.0.1 puro, fuente oficial:
https://github.com/hukkin/tomli/tree/2.0.1/src/tomli

Archivos originales __init__.py, _parser.py, _re.py y _types.py, sin cambios.
Licencia MIT original incluida en revlogs/_vendor/tomli/LICENSE y en el wheel.
Solo se utiliza en Python 3.10; Python 3.11+ utiliza tomllib de la biblioteca estándar.
No se requieren paquetes externos al ejecutar revlogs. Ruff/mypy propios excluyen
el código de terceros; las pruebas funcionales verifican su uso real en Python3.10.
