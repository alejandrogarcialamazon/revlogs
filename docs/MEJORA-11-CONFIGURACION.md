# Mejora 11: configuración TOML reutilizable

Fecha: 13/11/2026. Publicación autorizada: 20:35 Buenos Aires.

`--config archivo.toml` carga explícitamente una configuración UTF-8 de hasta
64 KiB. No hay búsqueda automática, includes, interpolación de variables ni
ejecución de código. La tabla [revlogs] contiene opciones con sus nombres CLI
en snake_case: paths/output, include/exclude, recursive/strict/include_reports,
format/level_field/numeric_levels, compression/encoding/decode_errors, patrones,
literales, umbrales y límites. Las listas son arrays de cadenas, no comandos.

Precedencia: argumentos CLI > TOML > valores predeterminados. Las listas de CLI
reemplazan las de TOML. Los posicionales reemplazan paths. Los flags booleanos
admiten --no-recursive, --no-strict, --no-include-reports y --no-verbose para
anular valores true. Las rutas del archivo se resuelven respecto del directorio
del TOML, con expansión de ~; las rutas de CLI siguen siendo relativas al cwd.
Una salida fija conserva la protección contra sobrescritura del programa.

schema_version es 1 (valor predeterminado si se omite). Se rechazan tablas,
claves, versiones, tipos y elecciones desconocidos; no se ignora un TOML inválido
aunque CLI pudiera reemplazar su valor. Los límites y patrones conservan su
validación semántica. Un fallo de configuración termina con código 2.

Python 3.11+ usa tomllib. Para Python 3.10 se incluye tomli 2.0.1 puro con su
licencia MIT y procedencia documentada; no se agregan dependencias de ejecución.
El código de terceros se mantiene separado del código propio y se incluye en
el wheel, junto a su licencia. Ver docs/VENDORED-TOMLI.md.

```toml
schema_version = 1
[revlogs]
paths = ["./logs"]
recursive = true
format = "auto"
include = ["*.log", "*.gz"]
```

```bash
python3 -m revlogs --config settings.toml --no-recursive --include '*.log'
```

Doce regresiones cubren precedencia, listas, booleanos, rutas relativas, esquema,
tipos, tamaño y sintaxis. Se valida el fallback real en una copia temporal de
.89 con Python 3.10, sin sudo ni instalar dependencias. También se comprueban
Ruff, mypy, clon limpio, empaquetado, CLI instalada y presencia de licencia.

Resultado comprobado: 138 pruebas locales y 138 remotas con Python 3.10.12,
incluida la carga real por tomli vendorizado. Ruff/formato/mypy y wheel/sdist
aprobados; el wheel incluye el parser y su licencia. No se instalaron paquetes
globales ni se copiaron credenciales al host de pruebas.
