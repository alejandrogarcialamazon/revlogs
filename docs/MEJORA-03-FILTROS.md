# Mejora 3: evitar contaminación de conteos por reportes

Fecha: 06/11/2026. Publicación autorizada: 17:10 Buenos Aires.

## Problema y cambio

Al analizar un directorio que contenía un reporte anterior, sus ejemplos volvían
a contarse como eventos originales. Un log con dos errores y una advertencia
podía pasar a seis errores y tres advertencias después de guardar el reporte.

El lector ahora reconoce una marca reservada al principio de los nuevos reportes:
`<!-- revlogs:report v1 -->`. También reconoce el prefijo de reportes antiguos
`# Reporte de análisis de logs`, seguido de una línea vacía e `Inicio: `.
Lee como máximo 256 bytes para reconocerlos. No depende del nombre ni la extensión;
un log Markdown normal sigue siendo elegible. La lectura del log continúa siendo
incremental. Las exclusiones son selección deliberada y no generan incidencias.

La opción `--include-reports` desactiva este reconocimiento por petición explícita.
Los patrones `--include` y `--exclude` son repetibles, sensibles a mayúsculas y
se comparan mediante fnmatch con nombre o ruta relativa POSIX a cada entrada.
`*` también puede coincidir con separadores; no es un glob de shell recursivo.
Se recorre un directorio solamente con `--recursive`. Las exclusiones prevalecen
sobre las inclusiones y podan directorios. El destino del reporte actual sigue
excluido incluso al usar `--include-reports`.

## Ejemplo

```bash
python3 -m revlogs ./logs -r --include '*.log' --exclude 'archive' -o ./logs/uno.md
python3 -m revlogs ./logs -r --include '*.log' --exclude 'archive' -o ./logs/dos.md
```

Las dos ejecuciones mantienen los conteos del log original. Un archivo que
comience exactamente con una cabecera reservada se tratará como reporte; puede
analizarse deliberadamente con `--include-reports`.

## Pruebas

50 pruebas totales, con 12 regresiones nuevas: nombre personalizado, formato
antiguo, Markdown real, inclusión explícita de reportes, filtros, precedencia,
poda, rutas relativas, exclusión exacta de directorios, CLI repetida, recursión
y patrón vacío. Se validan también Ruff, mypy estricto, compilación y snapshot
remoto Python 3.10.12 en una copia temporal, sin sudo ni cambios de servicios.
La evidencia operativa permanece en reports/, fuera de Git. El push se ejecuta
con SHA fijo y el asunto `Publicacion 06/11/2026 17:10`.
