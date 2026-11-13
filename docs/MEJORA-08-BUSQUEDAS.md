# Mejora 8: literales y regex con ejecución acotada

Fecha: 13/11/2026. Publicación autorizada: 18:55 Buenos Aires.

## Cambio

`--error-literal TEXT` y `--warning-literal TEXT` agregan búsquedas sin interpretar
metacaracteres. Son repetibles, no distinguen mayúsculas y mantienen las reglas
de severidad predeterminadas. Las alternativas no superpuestas de una categoría
no duplican coincidencias por literales repetidos. Si solo se usan literales y
reglas fijas, se ejecutan localmente, sin procesos adicionales. Si se agregan
regex personalizadas, todas las categorías se evalúan en el worker aislado.

Las regex personalizadas de --error-pattern/--warning-pattern se validan y
ejecutan en un proceso separado mediante multiprocessing spawn. Nunca se compilan
en el proceso principal. El worker no recibe descriptores ni rutas de logs: solo
el texto de cada línea ya leído por la apertura segura. Las reglas predeterminadas
siguen siendo regex fijas locales; un literal no se transforma en regex libre.

El timeout predeterminado de evaluación es 0,5 segundos por línea para ambas
categorías, configurable mediante --regex-timeout en (0,60]. El arranque y la
compilación tienen límite separado de cinco segundos. --regex-memory-mib fija
RLIMIT_AS del worker, por defecto 256 MiB (64–4096), respetando límites existentes
más bajos. Se admiten hasta 64 patrones/literales entre ambas categorías, con
4096 caracteres por entrada. Se rechazan literales vacíos y regex que coincidan
con texto vacío. Las coincidencias de longitud cero se ignoran.

## Fallos y resultados

Si una regex excede el tiempo o falla su worker, el archivo queda parcial y el
scan se detiene con incidencia bloqueante y código 2, preservando los conteos
anteriores. La línea fallida no aporta coincidencias parciales por categoría.
El worker se termina y se liberan proceso y canal al cerrar la sesión, incluso
tras timeout. La instancia puede reutilizarse en un scan posterior con otra sesión.
Los presupuestos de línea, bytes, recorrido y evidencias de la mejora 7 siguen
aplicándose. Los límites no son un plazo global de E/S ni garantizan tiempo real
bajo fallos del sistema operativo; spawn/IPC y cierre añaden latencia.
Al integrar regex personalizadas desde scripts Python, el punto de entrada debe
ser importable y estar protegido por `if __name__ == '__main__':`, como requiere
spawn. Para sesiones interactivas sin ese soporte, usar la CLI o literales.

```bash
python3 -m revlogs ./logs --error-literal 'connection failed [retry]'
python3 -m revlogs ./logs --error-pattern '(?i:failed|panic)' --regex-timeout 0.2
```

## Pruebas

Diez regresiones cubren metacaracteres literales, reglas predeterminadas,
duplicados, ausencia de worker para literales, regex normales y limpieza de
procesos, backtracking catastrófico, CLI acotada con timeout externo, errores
de sintaxis, tamaño excesivo y parámetros inválidos. Se comprueban suite,
Ruff/formato/mypy, copia remota temporal con Python 3.10, clon limpio y wheel
instalado. La evidencia operativa permanece en reports/, fuera de Git.

Resultado comprobado: **93 pruebas locales y 93 remotas** en Python 3.10.12,
Ruff/formato/mypy aprobados. El smoke de distribución también ejecuta una regex
catastrófica desde la CLI instalada, fuera del fuente, y exige código 2 y reporte
de timeout dentro de ocho segundos. Las copias temporales remotas se eliminan
sin sudo ni instalaciones globales. La CI real del commit se ejecutará tras el
push autorizado; no se anticipa su resultado.
