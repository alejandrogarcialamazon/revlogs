# Cambios

## Mejoras 11 y 12 — 2026-11-13

- Configuración TOML validada con precedencia CLI, rutas relativas y compatibilidad Python3.10.
- Reportes JSON/CSV de esquema v1 y exportaciones simultáneas con exclusión de reportes propios.

## Mejoras 9 y 10 — 2026-11-13

- Parsers de severidad JSONL y syslog con PRI, modo auto y errores de parseo explícitos.
- Lectura gzip por descriptor, codificaciones configurables y políticas de pérdida visibles.

## Mejoras 7 y 8 — 2026-11-13

- Presupuestos de lectura, recorrido, muestras e incidencias y estado parcial explícito.
- Búsqueda literal y regex personalizadas en proceso separado con timeout y memoria acotada.

## Mejoras 5 y 6 — 2026-11-13

- Estados operativos: rutas predeterminadas opcionales, selección vacía y modo estricto.
- Apertura Linux validada por descriptor, sin seguir symlinks ni reabrir el log por nombre.
- Pruebas de sustitución, FIFO sin bloqueos, rotación y liberación de recursos.

## Mejora 4 — 2026-11-06

- GitHub Actions para pruebas Python 3.10–3.14, Ruff, mypy y empaquetado.
- Smoke test del wheel instalado en un entorno temporal fuera del fuente.
- Dependencias de desarrollo fijadas y permisos de CI limitados a lectura.

## Mejora 3 — 2026-11-06

- Exclusión automática de reportes por marca/cabecera, incluidos nombres propios.
- Inclusiones/exclusiones glob repetibles y poda de directorios excluidos.
- Regresiones de conteos estables y conservación de logs en formato Markdown.

## Mejora 2 — preparada el 2026-11-05

- Diagnóstico sanitizado de autenticación GitHub, identidad, helper HTTPS,
  instrucciones globales de Codex/OpenCode y perfil github cargado por OpenCode.
- Pruebas aisladas de fallos, overrides y ausencia de herramientas.
- Guía de uso entre sesiones y recuperación sin duplicar credenciales.

## 1.0.0 — Preparación de publicación, 2026-11-05

- Analizador modular de errores y advertencias, lectura incremental y Markdown.
- CLI configurable, tratamiento de fallos parciales y codificación UTF-8/latin-1.
- Licencia MIT, metadatos de distribución y documentación de publicación.
- Publicación diferida de commits explícitos, con validación y comprobantes.

Esta es una versión inicial. Los filtros para evitar reprocesar reportes previos,
los parsers estructurados y las demás mejoras del informe siguen pendientes.
