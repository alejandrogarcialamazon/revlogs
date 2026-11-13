# Mejora 6: apertura segura de logs en Linux

Fecha: 13/11/2026. Push autorizado: 18:25 Buenos Aires.

## Problema

Validar con lstat y abrir después por nombre deja una ventana de sustitución.
Además, la cabecera del reporte se abría por separado del análisis: una rotación
o sustitución podía cambiar el archivo entre esas dos operaciones.

## Implementación

`safe_io.open_log` recorre los componentes mediante descriptores de directorio
y O_NOFOLLOW. Obtiene primero un descriptor O_PATH, que no abre FIFO ni
dispositivos para lectura. fstat exige archivo regular y el mismo dispositivo e
inodo que se observaron durante el descubrimiento. Solo después convierte ese
descriptor en uno de lectura a través de `/proc/self/fd` del propio proceso y
revalida su identidad. Los descriptores tienen CLOEXEC y la lectura NONBLOCK.

`discover_sources` entrega un LogSource con el descriptor ya validado. El
reconocimiento de reportes y el análisis usan el mismo stream; no hay reapertura
por nombre. Se cierran descriptores al completar, interrumpir o fallar la lectura.
`discover_files` conserva la API de rutas orientativa; el analizador utiliza
fuentes abiertas. `read_lines(Path)` también aplica la apertura segura.

Las entradas inseguras se notifican como incidencias bloqueantes (`unsafe_input`).
La validación real al abrir complementa el chequeo previo de permisos. Una ruta
con componentes simbólicos se rechaza incluso si termina en un archivo regular.
No hay fallback a una apertura insegura si faltan las capacidades necesarias.

## Alcance y límites

Esta función requiere Linux con O_PATH y `/proc/self/fd` disponible. Los entornos
restringidos que no permitan convertir el descriptor fallan de forma cerrada.
Los directorios se enumeran para descubrir candidatos; el control de apertura
protege la lectura del contenido, no constituye un confinamiento de directorios.
La identidad no congela los bytes de un log activo: escrituras o truncamientos
del mismo inodo siguen siendo posibles. Usar copias estables para una auditoría
reproducible. Una rotación posterior a la apertura conserva el archivo abierto;
las nuevas entradas requieren una nueva ejecución.

## Pruebas

Trece regresiones cubren sustitución por symlink, otro archivo y FIFO, componente
padre sustituido por symlink, lectura del descriptor original tras rotación,
cierre temprano, fugas de descriptores, ausencia de procfs, FIFO directa,
plataforma no soportada, fallo de creación del stream, bucle simbólico e
integración del scanner ante sustitución previa a la cabecera. Las
pruebas de FIFO usan subprocesos con timeout para detectar bloqueos.

Se verifica la suite completa, Ruff, formato, mypy estricto, compilación,
empaquetado, clon limpio y wheel instalado. La prueba en el host remoto usa una
copia temporal con Python 3.10, sin sudo, credenciales copiadas ni cambios de
servicios. Los resultados operativos se conservan en reports/, fuera de Git.

Resultados comprobados el 13/11: **71 pruebas locales y 71 remotas** aprobadas
en Python 3.10.12, incluyendo compilación y CLI. Ruff, formato y mypy estricto
aprobados; wheel/sdist construidos y smoke del wheel instalado con conteos,
umbrales, reportes repetidos y pip check aprobado. No se instalaron componentes
globales en el host de pruebas. La CI hospedada de este commit se ejecutará tras
su push de las 18:25; no se da por aprobada antes de publicarlo.

Referencias: [Linux open(2), O_PATH y O_NOFOLLOW](https://man7.org/linux/man-pages/man2/open.2.html)
y [Python 3.10: os.open y descriptores](https://docs.python.org/3.10/library/os.html#os.open).
