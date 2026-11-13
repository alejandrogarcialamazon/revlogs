# Operación y distribución

Instalar en un entorno virtual con permisos de lectura limitados a los logs que
se necesitan. No es necesario ejecutar revlogs como root. Salidas: 0 análisis
correcto; 1 umbral --fail-on alcanzado; 2 error operativo; 130 interrupción.
`--strict` convierte avisos operativos en fallos. No sobrescribe reportes existentes.

Para tareas cron/systemd usar rutas absolutas y nombres de reporte únicos. Guardar
checkpoints fuera del directorio de logs; respaldarlos junto con la configuración.
Cada tarea debe usar su propio estado. Revisar las limitaciones de redacción e
incremental en MEJORA-13-REDACCION.md y MEJORA-14-INCREMENTAL.md.

## Preparar una release verificable

Desde un checkout limpio del commit aprobado:

```bash
python3 -m build --outdir dist-release
python3 tools/check_distribution.py dist-release
python3 tools/release_checksums.py dist-release
python3 tools/release_checksums.py dist-release --verify
```

Para verificar con sha256sum: `cd dist-release && sha256sum --check SHA256SUMS`.
Publicar wheel, sdist y SHA256SUMS juntos. El checksum detecta modificaciones;
no sustituye una firma ni autentica por sí solo al publicador. No subir a PyPI
sin una autorización específica. La publicación del código no crea automáticamente
una release de GitHub ni cambia instalaciones existentes.

Ejemplo sintético: `python3 -m revlogs examples/sample.log --redact -o demo.md`.
