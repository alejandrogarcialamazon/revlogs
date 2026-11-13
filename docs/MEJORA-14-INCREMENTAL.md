# Mejora 14: análisis incremental con checkpoints

Fecha: 13/11/2026. Horario solicitado: 20:52 Buenos Aires (junto con mejora 13).

`--state /ruta/privada/checkpoint.json` guarda identidad dispositivo/inodo, posición
binaria, número de línea y hash de los primeros 4096 bytes ya procesados. No guarda
contenido del log. Admite TOML state relativo al archivo de configuración.

```bash
python3 -m revlogs /var/log/syslog --state ~/.local/state/revlogs/syslog.json -o primera.md
python3 -m revlogs /var/log/syslog --state ~/.local/state/revlogs/syslog.json -o siguiente.md
```

La segunda ejecución cuenta únicamente líneas nuevas completas; conserva números
de línea originales. La última línea sin salto final queda pendiente. Reinicia
cuando cambia el inodo, disminuye el tamaño o cambia el prefijo procesado. Un
reescrito que conserve identidad, tamaño suficiente y el mismo prefijo puede no
ser detectado: para rotación se recomienda rename y crear otro archivo.

Checkpoint atómico con permisos 0600 y lock no bloqueante; estado y lock quedan
excluidos de la selección. No avanza ante errores operativos ni fallo al generar
reportes. Un fallo posterior a crear reportes pero anterior a guardar estado puede
repetir eventos: semántica de al menos una vez. Requiere archivos sin comprimir,
UTF-8/latin-1/ASCII; gzip y UTF-16/32 se rechazan. Estado corrupto se rechaza.
Cambiar reglas, formato, codificación o redacción requiere otro archivo de estado.
No acumula totales históricos: cada reporte describe el delta de esa ejecución.

Pruebas: append, ejecución sin cambios, línea incompleta, rotación, truncamiento,
reescritura del prefijo, permisos, corrupción, exclusión mutua y checkpoint CLI.
