# Mejora 10: gzip y codificación configurable

Fecha: 13/11/2026. Publicación autorizada: 19:59 Buenos Aires.

La lectura gzip se realiza en streaming sobre el descriptor regular ya validado;
no se reabre la ruta ni se extraen archivos. --compression auto detecta magic
gzip o extensión .gz; none y gzip fuerzan el modo. Una extensión .gz con cabecera
inválida produce error, no se interpreta como texto. Se aceptan miembros gzip
concatenados. Corrupción, CRC inválido y truncamiento generan compression_error.
Los reportes se reconocen y omiten después de descomprimirlos.

Los presupuestos existentes de línea/archivo/total se aplican a bytes
descomprimidos, antes de decodificar. --max-compressed-bytes (1 GiB por defecto)
limita además el avance sobre la entrada comprimida, incluidas sus cabeceras.
La anticipación permite un byte adicional para detectar el exceso. Los límites
no son un plazo global de E/S. Un corte conserva resultados ya emitidos y produce
error operativo. No se cargan archivos completos ni se usa gzip.decompress.

--encoding auto detecta BOM UTF-16/32, o usa UTF-8 con fallback latin-1 por línea,
conservando compatibilidad con archivos mixtos. Se admiten explícitamente ASCII,
UTF-8, latin-1, cp1252, UTF-16 y UTF-32 con variantes LE/BE. Las formas UTF-16/32
sin endian requieren BOM; las formas LE/BE lo permiten ausente. El lector respeta
la alineación de unidades, incluso cuando un carácter contiene un byte 0A que no
es un salto de línea. Las codificaciones con estado no están soportadas.

--decode-errors strict es el valor predeterminado: bytes inválidos para una
codificación explícita detienen el archivo con decode_error y estado parcial.
replace/ignore son decisiones explícitas: registran decode_loss no bloqueante y
cuentan las líneas afectadas. --strict convierte esos avisos en fallo. El fallback
latin-1 de auto no pierde bytes y se registra con el contador existente.
El reporte incluye compresión, codificación resuelta y líneas con pérdida.

```bash
python3 -m revlogs ./logs -r --include '*.gz' --format auto
python3 -m revlogs app.log --encoding cp1252
python3 -m revlogs utf16.log --encoding utf-16
python3 -m revlogs app.log.gz --encoding utf-8 --decode-errors replace
```

Dieciocho regresiones cubren gzip por nombre/magic, concatenación, corrupción,
límites comprimidos y descomprimidos, BOM/endian, falsos saltos, fallos estrictos,
pérdida explícita, reportes comprimidos y JSON gzip. Las pruebas remotas usan una
copia temporal con Python 3.10, sin sudo ni instalaciones globales. La evidencia
operativa se conserva en reports/ y las pruebas incluyen wheel instalado.

Resultados: 126 pruebas locales y 126 remotas en Python 3.10.12, con estilo,
formato y tipado aprobados. El smoke de instalación incluye gzip con JSON UTF-16,
además de conteos, reportes repetidos y timeout real de regex. En auto, las firmas
BOM ambiguas priorizan UTF-32; --encoding utf-16 permite indicar la intención.
