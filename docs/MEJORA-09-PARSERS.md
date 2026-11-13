# Mejora 9: severidad de eventos JSON y syslog

Fecha: 13/11/2026. Publicación autorizada: 19:50 Buenos Aires.

`--format text` conserva el conteo tradicional de palabras/patrones. Los nuevos
modos json, syslog y auto clasifican severidad por campos estructurados para
evitar contar un ERROR mencionado en el mensaje de un evento INFO.

JSON exige un objeto por línea (NDJSON/JSONL). Busca level, severity y log.level;
`--level-field` es repetible y reemplaza esa lista. Se admiten claves con puntos
y rutas de objetos anidados, con preferencia por la clave literal existente.
Si varios campos configurados presentan niveles contradictorios, se rechaza
la línea. También se rechazan claves duplicadas, tipos inválidos y niveles
desconocidos. No se infiere el nivel desde el mensaje ni se ejecutan expresiones
del usuario para acceder a campos. Se admiten hasta 16 campos de 128 caracteres.

ERROR/ERR/CRITICAL/CRIT/FATAL/ALERT/EMERG son errores; WARNING/WARN, advertencias.
INFO/NOTICE/DEBUG/TRACE y sus alias no aportan coincidencias. Cada evento
estructurado aporta como máximo una ocurrencia, sin analizar su mensaje.
`--numeric-levels python` interpreta 0/10/20/30/40/50; syslog interpreta 0–7.
Los nombres de nivel no distinguen mayúsculas. Booleanos y null no son niveles.

Syslog clasifica PRI entre 0 y 191, usando PRI módulo 8: 0–3 error, 4 warning,
5–7 informativo. Soporta la clasificación de mensajes con prefijo PRI de
RFC3164/5424; no valida todos los campos de sus cabeceras ni adivina el nivel
de syslog sin PRI. Auto detecta objetos que empiezan por { y candidatos <dígito;
el resto usa texto. Un candidato estructurado inválido no cae silenciosamente
al buscador de palabras. Regex/literales se aplican solo al texto, y la CLI
rechaza combinarlos con modos exclusivamente json/syslog.

Los fallos de parseo son incidencias bloqueantes y marcan el archivo parcial,
pero se continúa con las líneas siguientes. Se mantienen sus números originales
y evidencias. El reporte distingue líneas estructuradas, texto y errores de
parseo. Se conservan los límites de recursos y el tratamiento UTF-8/latin-1.

```bash
python3 -m revlogs app.jsonl --format json --level-field event.level
python3 -m revlogs syslog.txt --format syslog
python3 -m revlogs ./logs -r --format auto
```

Quince regresiones cubren falsos positivos, eventos únicos, niveles anidados,
campos propios, datos inválidos, duplicados, contradicciones, números, PRI,
mezcla de formatos y CLI. Se valida también suite, tipado, empaquetado, instalación
y copia remota temporal sin sudo. La evidencia operativa queda en reports/.
