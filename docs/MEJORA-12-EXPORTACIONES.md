# Mejora 12: exportaciones JSON y CSV, esquema v1

Fecha: 13/11/2026. Publicación autorizada: 20:40 Buenos Aires.

--report-format markdown|json|csv selecciona el formato primario (Markdown por
defecto). --json-output y --csv-output agregan exportaciones del mismo ScanResult,
sin repetir el análisis. --format sigue seleccionando el formato de entrada.
TOML admite report_format/json_output/csv_output con la misma precedencia y rutas
relativas de la mejora 11. Las extensiones deben concordar con cada formato.

```bash
python3 -m revlogs ./logs -o report.md --json-output report.json --csv-output report.csv
python3 -m revlogs ./logs --report-format json -o report.json
```

## Contrato JSON

Objeto raíz con report_kind="revlogs", schema_version=1, metadata, files e issues.
metadata contiene started_at/finished_at ISO8601 y summary: errores, warnings,
archivos, líneas, bytes, estado operativo, modo estricto y reducción de detalles.
files incluye ruta, estado completo/parcial, compresión/codificación, incidencias
de parseo/decodificación y categorías ERROR/WARNING. Cada categoría contiene
occurrences, matching_lines, omitted_lines y evidence (line_number/text/occurrences).
issues incluye path/message/code/blocking. JSON conserva el texto y escapa
caracteres de control/Unicode; no escribe NaN ni serializa rutas como objetos.

## Contrato CSV

CSV con cabecera revlogs_report,schema_version,record_type,... y filas etiquetadas:
summary (metric/value), metadata (fechas), file (ruta/estado), category (conteos),
evidence (muestras) e issue (incidencias). Todas las filas tienen versión1 y
revlogs_report=revlogs. Para obtener totales, filtrar summary; no sumar category
y evidence entre sí. Los valores booleanos se representan como True/False.
Delimitador coma, comillas estándar y CRLF preservan comas/comillas/saltos internos.
Las celdas de texto que podrían ser fórmulas reciben apóstrofo inicial; controles
no imprimibles se representan mediante escapes. Para texto original usar JSON.

## Integridad y recursos

Los renderers producen fragmentos en streaming, un archivo/registro a la vez,
sin construir un JSON global duplicado. Las muestras y límites son los mismos que
en consola/Markdown. Se reconocen las firmas de los nuevos reportes para no volver
a analizarlos, incluso con nombres personalizados. La escritura sigue siendo
privada (0600), atómica por archivo y sin sobrescritura; se rechazan destinos
duplicados o existentes antes del scan. Un fallo al escribir un reporte posterior
puede dejar reportes anteriores completos: no se promete una transacción de lote.

Quince regresiones verifican paridad de métricas, evidencia, CSV, inyección de
fórmulas, outputs simultáneos, primaria JSON/CSV, exclusiones, rutas duplicadas,
sobrescritura, fallos parciales, omisiones, Unicode y configuración TOML.
Se validan suite, estilo/tipado, clon limpio, wheel instalado y copia temporal
remota con Python3.10. Los resultados operativos permanecen fuera de Git.

Resultado comprobado: 153 pruebas locales y 153 remotas, Ruff/formato/mypy,
construcción y smoke de instalación. Este último carga TOML con la CLI instalada
y compara los conteos de JSON/CSV, además de probar gzip/UTF-16 y timeout de regex.
