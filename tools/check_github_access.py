"""Comprueba acceso GitHub compartido sin leer ni modificar credenciales."""

import argparse
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class CommandResult:
    code: int
    output: str = ""


def command(arguments: list[str]) -> CommandResult:
    environment = os.environ.copy()
    environment.update(GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    try:
        process = subprocess.run(
            arguments,
            text=True,
            capture_output=True,
            env=environment,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return CommandResult(2)
    # El caller solo interpreta salidas explícitas; nunca muestra stdout/stderr.
    return CommandResult(process.returncode, process.stdout)


Runner = Callable[[list[str]], CommandResult]


def instructions_check(name: str, path: Path) -> Check:
    try:
        content = path.read_text(encoding="utf-8")
        ready = "gh auth status" in content and "gh api user" in content
    except (OSError, UnicodeError):
        ready = False
    return Check(
        name,
        ready,
        "Instrucciones de verificación presentes"
        if ready
        else "Faltan instrucciones legibles para verificar cuenta y autenticación",
    )


def inspect_access(
    *,
    account: str,
    gh: str,
    codex_home: Path,
    opencode_home: Path,
    opencode: str,
    auth_only: bool = False,
    runner: Runner = command,
) -> list[Check]:
    """Valida entorno actual; no afirma acceso para otros usuarios o máquinas."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", account):
        raise ValueError("Nombre de cuenta GitHub inválido")
    checks: list[Check] = []
    authentication = runner([gh, "auth", "status"])
    checks.append(
        Check(
            "github_auth",
            authentication.code == 0,
            "Autenticación disponible"
            if authentication.code == 0
            else "No se pudo autenticar: verificar red, keyring y sesión local de gh",
        )
    )
    identity = runner([gh, "api", "user", "--jq", ".login"])
    correct_account = identity.code == 0 and identity.output.strip() == account
    checks.append(
        Check(
            "github_account",
            correct_account,
            "Cuenta esperada confirmada"
            if correct_account
            else "La cuenta no pudo confirmarse o no coincide",
        )
    )
    if auth_only:
        return checks
    helper = runner(
        ["git", "config", "--get-all", "credential.https://github.com.helper"]
    )
    checks.append(
        Check(
            "git_helper",
            helper.code == 0 and "gh auth git-credential" in helper.output,
            "Se requiere el helper de GitHub CLI para HTTPS",
        )
    )
    override = codex_home / "AGENTS.override.md"
    try:
        use_override = override.is_file() and bool(override.read_text().strip())
    except (OSError, UnicodeError):
        # Si existe un override ilegible, no afirmar que se cargará el AGENTS base.
        use_override = True
    codex_rules = override if use_override else codex_home / "AGENTS.md"
    checks.append(instructions_check("codex_rules", codex_rules))
    checks.append(instructions_check("opencode_rules", opencode_home / "AGENTS.md"))
    # Introspección del propio CLI: admite configuraciones JSON/JSONC y plugins.
    # No se abre opencode.json ni archivos de credenciales de proveedores.
    profile = runner([opencode, "debug", "agent", "github"])
    ready = False
    if profile.code == 0:
        try:
            config = json.loads(profile.output)
            ready = (
                isinstance(config, dict)
                and config.get("name") == "github"
                and config.get("mode") == "primary"
                and not config.get("disable", False)
            )
        except (ValueError, TypeError):
            pass
    checks.append(
        Check(
            "opencode_profile",
            ready,
            "Perfil principal github cargado"
            if ready
            else "OpenCode no confirmó el perfil principal github",
        )
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--gh", default=shutil.which("gh") or "gh")
    parser.add_argument("--opencode", default=shutil.which("opencode") or "opencode")
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))),
    )
    parser.add_argument(
        "--opencode-home",
        type=Path,
        default=Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "opencode",
    )
    parser.add_argument("--auth-only", action="store_true")
    args = parser.parse_args()
    try:
        checks = inspect_access(
            account=args.account,
            gh=args.gh,
            codex_home=args.codex_home.expanduser(),
            opencode_home=args.opencode_home.expanduser(),
            opencode=args.opencode,
            auth_only=args.auth_only,
        )
    except ValueError as exc:
        parser.error(str(exc))
    ready = all(check.ok for check in checks)
    print(
        json.dumps(
            {
                "status": "ready" if ready else "incomplete",
                "scope": "auth-only"
                if args.auth_only
                else "auth-and-global-configuration",
                "checks": [asdict(check) for check in checks],
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
