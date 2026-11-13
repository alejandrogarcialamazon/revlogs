# Mejora 5: estados operativos y rutas opcionales

Fecha: 13/11/2026. Push autorizado: 18:10 Buenos Aires.

Las distribuciones Linux no siempre tienen todas las rutas predeterminadas.
Su ausencia ahora se registra como aviso no bloqueante si se consigue procesar
algún archivo. Las rutas explícitas inexistentes, permisos insuficientes y
lecturas parciales siguen produciendo error operativo. `--strict` convierte
también los avisos en fallo. Si no se procesa ningún archivo, se devuelve 2.

Los resultados incluyen un código de incidencia y su carácter bloqueante.
Se distingue `empty_directory`, `empty_selection` (filtros/reportes excluidos)
y `no_readable_inputs`. El resumen y Markdown muestran estado y modo estricto.
El código 2 prevalece sobre los umbrales de errores/advertencias (código 1).
Un archivo vacío legible sí cuenta como procesado y no es una selección vacía.

```bash
python3 -m revlogs
python3 -m revlogs --strict
python3 -m revlogs ./logs --include '*.log'
```

Ocho regresiones cubren rutas predeterminadas y explícitas, modo estricto,
ausencia total, selección vacía, directorio vacío, permisos y avisos en Markdown.
La validación comprende suite, Ruff, formato, mypy, clon limpio, empaquetado y
CLI instalada. La prueba remota usa solo copias temporales y datos sintéticos,
sin sudo ni cambios de servicios. Los resultados operativos quedan en reports/.

Resultados comprobados el 13/11: 58 pruebas locales, 58 en Python 3.10.12 remoto
y 58 desde clon limpio. Ruff, formato, mypy estricto, wheel/sdist, CLI instalada
y pip check aprobados. El timer publicó el SHA autorizado a las 18:10:05;
se confirmó en GitHub sin adelantar la mejora 6.
La [ejecución de CI](https://github.com/alejandrogarcialamazon/revlogs/actions/runs/43508231415)
de ese commit finalizó correctamente.
