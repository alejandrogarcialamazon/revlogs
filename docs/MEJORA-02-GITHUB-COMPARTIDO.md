# Mejora 2: acceso compartido de GitHub entre sesiones

Fecha: 2026-11-05. Push autorizado:
**2026-11-06 10:15 America/Argentina/Buenos_Aires** (UTC-03).

## Implementación

Se reutiliza GitHub CLI y su almacén local de credenciales. No se instala otro
conector, no se duplican tokens y no se versiona configuración personal. El
helper HTTPS, las instrucciones globales de ambos clientes y el perfil principal
github de OpenCode ya existían. Se preservan los perfiles y reglas ajenos al
proyecto. El AGENTS.md del repositorio aporta instrucciones portables.

`tools/check_github_access.py` comprueba, sin cambios:

1. Disponibilidad de autenticación mediante `gh auth status`.
2. Identidad exacta con `gh api user --jq .login`.
3. Helper HTTPS de GitHub CLI.
4. Instrucciones globales de Codex, respetando AGENTS.override.md y CODEX_HOME.
5. Instrucciones globales de OpenCode, respetando XDG_CONFIG_HOME.
6. Carga real del perfil principal github mediante `opencode debug agent github`.

No abre archivos de credenciales ni opencode.json. Solo muestra comprobaciones
JSON sanitizadas, sin stdout/stderr arbitrarios. Los subprocesos tienen timeout
y no solicitan autenticación interactiva. Código 0 indica comprobaciones
aprobadas; 2 indica acceso/configuración incompletos.

## Uso en una nueva terminal

```bash
python3 tools/check_github_access.py --account TU_USUARIO
opencode --agent github
```

Para comprobar solo la autenticación del entorno actual:

```bash
python3 tools/check_github_access.py --account TU_USUARIO --auth-only
```

El acceso compartido corresponde al mismo usuario y máquina, con su keyring
desbloqueado y red disponible. No otorga acceso automático a sesiones remotas,
contenedores, otros usuarios ni sandboxes. La comprobación valida autenticación
y configuración global: no inicia conversaciones de IA ni certifica que una
política de sesión permita cualquier escritura.

## Recuperación cuando falte acceso

Primero distinguir red restringida de credencial inválida. Si falta realmente
autenticación, ejecutar en la estación:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
```

El usuario completa el navegador. No ejecutar `gh auth token`, copiar privadas
SSH ni trasladar credenciales al host de pruebas. Si cambia la configuración
global, iniciar sesiones nuevas para comprobar su carga.

## Validación

Resultados comprobados el 2026-11-05:

- 38 pruebas locales y 38 remotas aprobadas (26 previas y 12 del diagnóstico).
- La suite cubre cuenta equivocada, fallo de autenticación, overrides, reglas
  ausentes, perfil inválido/desactivado, modo auth-only, ejecutable ausente y
  timeout, sin usar credenciales reales en las pruebas unitarias.
- Ruff, mypy estricto y compilación aprobados. Wheel/sdist construidos.
- Dos terminales login nuevas, ejecutando fuera del proyecto: seis controles
  aprobados en cada una para la cuenta esperada.
- Un servicio transitorio de systemd confirmó los mismos seis controles,
  incluyendo el keyring existente y la carga real del perfil de OpenCode.
- Linux remoto Python 3.10.12: CLI, compilación y caso negativo de GitHub CLI
  ausente aprobados. El host remoto no tiene gh instalado; no se copiaron
  credenciales ni se afirmó que herede la autenticación de la estación.
- Streaming remoto: 200.000 líneas, 400.000 errores y 200.000 advertencias
  contados correctamente, con tres evidencias por categoría y 54.164 bytes de
  pico de asignaciones Python (no equivale al consumo total del proceso).

Las copias remotas se eliminaron al terminar; no se usó sudo ni se instalaron
herramientas globales. La evidencia saneada permanece en `reports/`, excluida de
Git. La publicación depende del commit de la mejora 1 y utiliza exclusivamente
el commit fijado para esta entrega. No se iniciaron conversaciones adicionales
de IA: se verificaron terminales nuevas, configuración e introspección del CLI.

## Referencias

- [Instrucciones globales de Codex](https://developers.openai.com/codex/guides/agents-md/).
- [Reglas globales de OpenCode](https://opencode.ai/docs/rules/).
- [Perfiles de OpenCode](https://opencode.ai/docs/agents/).
- [Helper Git de GitHub CLI](https://cli.github.com/manual/gh_auth_setup-git).
