# Mejora 1: preparar la publicación pública

Fecha: 2026-11-05. Repositorio autorizado:
https://github.com/alejandrogarcialamazon/revlogs, visibilidad pública.

## Alcance

Se prepara la versión inicial existente, con licencia MIT, metadatos de paquete,
instrucciones del proyecto y exclusiones de configuración privada. No se incluyen
logs reales ni reportes de pruebas. La mejora no cambia las reglas del analizador.
El problema conocido de reprocesamiento de reportes queda para la mejora 3.

## Publicación diferida

Push autorizado: **2026-11-05 21:50 America/Argentina/Buenos_Aires** (UTC-03).
Crear el repositorio vacío es independiente de publicar su contenido. El commit
raíz se fija en un manifiesto privado; el push no usa HEAD. La mejora 2 permanece
local hasta su horario propio. No se usan pushes forzados.

`tools/scheduled_push.py` valida el snapshot antes de publicar, comprueba cuenta,
remoto, visibilidad pública, padre del commit y estado de main. Impide publicar
antes del horario, evita sobrescribir avances ajenos y admite reintentos cuando
el commit ya fue publicado. Dos ejecuciones se serializan con flock. Los
comprobantes locales distinguen ensayos sin push de publicaciones confirmadas.

Los timers de usuario usan fecha y zona explícitas, Persistent=true y reintentos
limitados. Si la estación está apagada, el timer puede ejecutarse al recuperarla;
no es garantía de entrega exacta. Requiere estación, proyecto, red y credenciales
disponibles. Las rutas operativas y hashes se registran en
`reports/PUBLICACIONES-PROGRAMADAS.md`, excluido de Git.

## Validación

Resultados comprobados el 2026-11-05:

- 26 pruebas locales aprobadas: 17 del analizador y nueve del publicador con
  remotos Git temporales (primer push, cadena, reintentos, fecha, cuenta,
  divergencias y ensayos sin publicación).
- Las mismas 26 pruebas aprobadas en Linux remoto con Python 3.10.12.
- Compilación, ayuda de CLI y análisis sintético UTF-8/latin-1 remotos aprobados;
  resultado esperado: dos errores y dos advertencias, con un aviso de fallback.
- Ruff y mypy estricto aprobados; cambios de formato sin alterar las reglas.
- Wheel y sdist construidos; instalación de wheel sin red en un entorno nuevo,
  CLI fuera del árbol fuente, análisis sintético y pip check aprobados.
- Wheel sin herramientas de desarrollo, pruebas ni configuración privada.
- Revisión de rutas publicables y patrones conocidos de secretos sin hallazgos.
- Repositorio GitHub creado y verificado público y vacío antes del horario.

El host remoto se usó únicamente con copias temporales y datos sintéticos, sin
sudo, instalación global ni cambios de servicios; las copias se eliminaron al
terminar. Evidencia operativa en `reports/validacion-*-mejora-01.json`, excluida de
Git. La clonación limpia del commit se valida antes de habilitar el timer. Un
timer activo no acredita un push futuro.
