# Mejora 15: distribución y documentación de revlogs 1.1.0

Fecha: 13/11/2026. Publicación solicitada: 20:58 Buenos Aires.

Versión 1.1.0 con ejemplos exclusivamente sintéticos, guía de contribución,
procedimiento operativo y preparación de wheel/sdist verificables con SHA-256.
`tools/release_checksums.py DIR` genera SHA256SUMS sin sobrescribir; `--verify`
recalcula los hashes y falla si cambian los paquetes, falta alguno o hay enlaces.
La lectura usa bloques de 1 MiB. No requiere bibliotecas de ejecución adicionales.

La distribución incluye documentación, pruebas, herramientas y ejemplos en sdist.
El wheel instala únicamente el paquete. No se publican logs reales ni archivos de
estado. La generación de paquetes es independiente del push: no hay publicación
implícita a PyPI ni creación automática de una release de GitHub.

Validación: suite completa local y en host autorizado, análisis estático, build
sdist/wheel, instalación en entorno limpio, CLI y verificación de checksums;
pruebas de manipulación de paquetes y manifiesto, archivos ausentes y streaming.

Resultado: 166 pruebas OK localmente y en Python 3.10 del host autorizado;
Ruff y mypy OK; wheel 1.1.0 instalado en venv limpio; SHA256SUMS generado y
verificado para wheel y sdist. Las mejoras 13/14 se publicaron a las 20:55:20
Buenos Aires, con retraso respecto de las 20:52 solicitadas.
