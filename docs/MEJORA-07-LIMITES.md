# Mejora 7: presupuestos de recursos

Fecha: 13/11/2026. Publicación autorizada: 18:45 Buenos Aires.

Se limita la lectura de cada línea con readline(size), antes de decodificarla.
Una línea que excede el máximo detiene ese archivo sin contar un fragmento como
línea completa. Los conteos anteriores se conservan, el archivo queda parcial
y una incidencia bloqueante produce código 2. No se consume el resto de la línea.

Valores predeterminados, configurables mediante CLI y ScanLimits:

| Opción | Valor |
| --- | ---: |
| --max-line-bytes | 1048576 |
| --max-file-bytes | 1073741824 |
| --max-total-bytes | 4294967296 |
| --max-files | 10000 |
| --max-entries | 100000 |
| --max-depth | 32 |
| --max-total-details | 10000 |
| --max-issues | 1000 |

El presupuesto global se comparte entre archivos. Los límites globales de bytes,
archivos y entradas detienen el scan. El límite por archivo permite seguir con
otros. La profundidad cuenta directorios bajo cada raíz y poda ramas profundas
con una incidencia. Los filtros deliberados siguen teniendo prioridad.
La profundidad admite 0–128 para mantener acotada la pila del recorrido.

Resultado comprobado: 83 pruebas locales y 83 remotas en Python 3.10.12,
Ruff/formato/mypy y wheel instalado aprobados. Las copias remotas se eliminan
al terminar, sin sudo ni instalaciones globales.

Los presupuestos de bytes cuentan el contenido solicitado al stream y permiten
un byte de anticipación para distinguir EOF de un límite excedido; no miden la
prefetch interna del sistema operativo ni los 256 bytes de inspección de cabecera.
Una entrada cuyo corte cae en mitad de línea no aporta coincidencias parciales.
Los límites no garantizan tiempo máximo de E/S en un filesystem bloqueado.

El límite global de evidencias solo reduce muestras: conserva todos los conteos
y no genera fallo. Las incidencias excedentes se contabilizan sin guardarlas;
se conserva si alguna era bloqueante, incluso con el listado ya completo.
Con --strict, también las incidencias omitidas no bloqueantes causan fallo.
El reporte incluye bytes leídos y las reducciones de detalle.

Doce regresiones verifican límites exactos y excedidos, resultados parciales,
presupuestos compartidos, profundidad, entradas, muestras, incidencias y memoria
ante una línea de 2 MB. Se comprueban suite, tipado, estilo, instalación y copia
remota temporal. La evidencia operativa se conserva fuera de Git en reports/.
