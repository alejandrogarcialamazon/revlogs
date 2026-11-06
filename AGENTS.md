# revlogs: instrucciones del proyecto

- Python >= 3.10; mantener el analizador sin dependencias de ejecución.
- Ejecutar `python3 -m unittest discover -s tests -v` tras cambios funcionales.
- Comprobar instalación y CLI desde una copia limpia antes de publicar.
- Documentar cada mejora en `docs/MEJORA-NN-*.md`.
- No versionar logs reales, reportes operativos, credenciales ni configuración
  personal de Codex/OpenCode.
- Los pushes programados publican commits fijos. No cambiar sus referencias ni
  reemplazarlas por HEAD sin una nueva instrucción del usuario.
- GitHub: usar la autenticación local de `gh`, comprobar la cuenta antes de
  operar y respetar los permisos de cada sesión. Nunca leer o copiar tokens.
