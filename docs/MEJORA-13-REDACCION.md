# Mejora 13: redacción optativa de evidencias

Fecha: 13/11/2026. Horario solicitado: 20:52 Buenos Aires (junto con mejora 14).

`--redact` oculta valores de password/passwd/secret/token/api_key/access_token,
Bearer, credenciales HTTP(S) y correos habituales. `--redact-literal TEXT` agrega
hasta 64 literales (4096 caracteres cada uno) y activa la redacción. TOML admite
redact y redact_literal. Para secretos propios conviene configurar literales en
un archivo privado, evitando el historial de shell.

Se cuenta sobre el original y se redacta antes de truncar y almacenar evidencia:
Markdown, JSON y CSV reciben el mismo texto protegido. No modifica el log original.
Las reglas son heurísticas, no garantizan anonimización completa: nombres de
archivo, mensajes operativos y formatos de secretos desconocidos requieren revisión.
Sin estas opciones se conserva el comportamiento anterior.

```bash
python3 -m revlogs examples/sample.log --redact -o informe.md
```

Pruebas: contraseñas entre comillas, JSON, Bearer, URL, correo, literales,
activación optativa y conservación de conteos antes de redacción/truncamiento.
