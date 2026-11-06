# revlogs

Analizador modular de logs de texto para Python 3.10 o posterior, sin dependencias
de ejecución. Cuenta errores y advertencias, muestra un resumen por archivo y
genera un reporte Markdown fechado. No modifica los logs.

Repositorio público: https://github.com/alejandrogarcialamazon/revlogs.
Licencia MIT. Estado: versión inicial; ver [CHANGELOG.md](CHANGELOG.md) y
[mejora 1: publicación](docs/MEJORA-01-PUBLICACION.md).
El [diagnóstico de acceso GitHub](docs/MEJORA-02-GITHUB-COMPARTIDO.md) permite
comprobar la configuración compartida de Codex y OpenCode sin leer credenciales.

## Uso

Desde este directorio, sin instalación:

```bash
python3 -m revlogs /var/log/syslog /var/log/nginx/error.log
python3 -m revlogs /ruta/logs --recursive --output reports/analisis.md
python3 -m revlogs
```

Sin rutas usa `/var/log/syslog`, `/var/log/messages`, `/var/log/auth.log`,
`/var/log/kern.log`, `/var/log/nginx/error.log` y `/var/log/apache2/error.log`.
Valida existencia y lectura; registra rutas no disponibles y continúa con las
restantes. El reporte también incluye esas incidencias. No requiere ejecutar
como root: usa una cuenta que tenga permisos sobre los logs elegidos.

Por defecto, los directorios se recorren solo en su primer nivel. `--recursive`
incluye subdirectorios. Se procesan sus archivos regulares de cualquier extensión,
exceptuando los reportes reconocidos de revlogs. No se siguen
enlaces simbólicos ni se leen dispositivos, sockets o FIFO. Las rutas repetidas y
los enlaces duros al mismo archivo se analizan una sola vez.

Los reportes se reconocen por una marca de contenido, incluso con nombres
personalizados; también se reconoce la cabecera de reportes anteriores. Los
archivos Markdown normales se conservan. `--include-reports` permite incluir
reportes de forma deliberada. `--include GLOB` y `--exclude GLOB` son repetibles:
se comparan con el nombre o ruta relativa POSIX a cada directorio de entrada,
sin distinguir separadores dentro de `*` y distinguiendo mayúsculas. Las exclusiones
prevalecen y permiten podar directorios. Usar comillas evita expansión del shell:

```bash
python3 -m revlogs ./logs -r --include '*.log' --include '*.log.1' --exclude 'archive'
```

Detalles y pruebas: [mejora 3](docs/MEJORA-03-FILTROS.md).

El reporte se guarda en `reports/revlogs_AAAAMMDD_HHMMSS_microsegundos.md`, salvo
que se indique `--output`. El destino debe terminar en `.md` y no existir. Se crean
los directorios necesarios y el archivo se publica completo con permisos `0600`.
La publicación usa un enlace duro en el mismo directorio: requiere un sistema de
archivos que los soporte. Un fallo no deja un reporte parcial ni sobrescribe otro
archivo. Los reportes contienen extractos de logs: elegir un destino apropiado
para esos datos.

También se puede instalar la CLI en un entorno virtual:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/revlogs --help
```

## Reglas y conteos

- Errores: palabras completas `ERROR`, `CRITICAL`, `FATAL`.
- Advertencias: palabras completas `WARNING`, `WARN`.
- Búsqueda sin distinción entre mayúsculas y minúsculas.
- `ERROR ERROR WARN` cuenta dos errores y una advertencia en una misma línea.
- `terror`, `warned` y `error_code` no coinciden con las reglas predeterminadas.
- Los conteos corresponden a palabras coincidentes, no a incidentes únicos.
  Las trazas de varias líneas no se agrupan automáticamente.

Agregar expresiones regulares sin cambiar el código:

```bash
python3 -m revlogs ./logs -r \
  --error-pattern '\b(?:failed|panic)\b' \
  --warning-pattern '\bdeprecated\b' \
  --max-details 100 --max-excerpt-chars 2000
```

Las opciones de patrones pueden repetirse y se suman a las reglas por defecto.
Dentro de cada categoría, las alternativas se combinan en una sola expresión:
se cuentan coincidencias no superpuestas, respetando el orden de alternativas de
Python. No se duplican coincidencias por patrones equivalentes. Los patrones
deben consumir texto; los que coincidan con la cadena vacía se rechazan y las
coincidencias de longitud cero en otros contextos se ignoran. Usar expresiones
confiables: las regex complejas pueden degradar mucho el tiempo de ejecución.

## Streaming y codificación

Cada archivo se lee una sola vez, línea por línea en binario. Se intenta UTF-8 y,
si una línea no es válida, se decodifica como latin-1 y se registra el fallback.
Esto permite archivos mixtos sin recontar líneas; no es detección automática de
codificación. UTF-16, logs comprimidos y formatos binarios no están soportados.

Por defecto se conservan las primeras 50 líneas de evidencia por archivo y
categoría, con extractos de hasta 1000 caracteres. `--max-details 0` conserva
solo métricas. El reporte indica cuántas líneas con coincidencias quedaron sin
detalle. Los conteos siempre incluyen todas las líneas leídas.

El consumo de memoria depende de la línea más larga y de las muestras/estadísticas
por archivo, no del tamaño completo de los logs. Una línea individual enorme sí
debe entrar en memoria. El análisis es secuencial. Los archivos activos pueden
cambiar durante la lectura: el reporte representa lo leído, no una instantánea;
para auditorías reproducibles, usar copias estables de los logs.

Si hay un fallo de lectura, se conservan los conteos parciales, se marca el archivo
como parcial y se continúa. La consola presenta métricas; `logging` envía avisos
a stderr. `--verbose` agrega el progreso por archivo.

## Automatización

```bash
python3 -m revlogs ./logs --fail-on error
python3 -m revlogs ./logs --fail-on warning
```

| Código | Significado |
| --- | --- |
| 0 | Análisis completado; sin umbral solicitado o sin coincidencias del umbral |
| 1 | Umbral alcanzado: `error` detecta errores; `warning` detecta cualquiera de las dos categorías |
| 2 | Argumentos inválidos, incidencias operativas, ninguna entrada analizable o fallo al escribir el reporte |
| 130 | Interrupción por teclado durante el análisis o la escritura |

El código 2 tiene prioridad sobre los umbrales. Las rutas por defecto que no
existan cuentan como incidencias operativas, aunque otros archivos se procesen.
El fallback a latin-1 es un aviso y no produce por sí solo un código 2.

## Arquitectura y pruebas

- `reader.py`: rutas por defecto, descubrimiento, permisos y lectura incremental.
- `analyzer.py`: expresiones regulares, conteos y evidencias limitadas.
- `models.py`: modelos tipados compartidos.
- `reports.py`: resumen de consola, renderer Markdown y escritura atómica.
- `cli.py`: argumentos, logging y códigos de salida.

Para nuevos formatos, implementar `ReportRenderer.render(result)` como un
iterador de fragmentos de texto y pasarlo a `write_report`. Para integrar desde
Python, usar `LogAnalyzer.scan()` y consultar `ScanResult`.

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas cubren conteos, categorías mixtas, muestras limitadas, codificación,
rutas repetidas, recursión, permisos, lecturas parciales, archivos especiales,
escape de Markdown, publicación del reporte y códigos de salida de la CLI.
