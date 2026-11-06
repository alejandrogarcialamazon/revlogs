"""Publica un commit aprobado y fechado, sin usar HEAD ni sobrescribir ramas."""

import argparse
import fcntl
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


def run(arguments: list[str], cwd: Path | None = None) -> str:
    environment = os.environ.copy()
    environment.update(GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    process = subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if process.returncode:
        # No registrar stdout/stderr arbitrarios de herramientas de autenticación.
        raise RuntimeError(f"Falló {Path(arguments[0]).name}: {process.returncode}")
    return process.stdout.strip()


def remote_head(repository: Path) -> str | None:
    text = run(["git", "ls-remote", "origin", "refs/heads/main"], repository)
    if not text:
        return None
    fields = text.split()
    if len(fields) != 2 or fields[1] != "refs/heads/main":
        raise RuntimeError("Respuesta ambigua para main remoto")
    return fields[0]


def validate_snapshot(repository: Path, commit: str) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=repository,
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="revlogs-approved-") as directory:
        root = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            for member in stream:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts:
                    raise RuntimeError("Ruta insegura en el snapshot")
                destination = root.joinpath(*name.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source = stream.extractfile(member)
                    if source is None:
                        raise RuntimeError("Archivo ilegible en el snapshot")
                    with source, destination.open("wb") as target:
                        while chunk := source.read(65536):
                            target.write(chunk)
                else:
                    raise RuntimeError("Enlaces/archivos especiales no publicables")
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], root)
        run([sys.executable, "-m", "revlogs", "--help"], root)


def publish(
    config: dict[str, Any], job_id: str, *, check_only: bool = False
) -> dict[str, Any]:
    job = config["jobs"][job_id]
    repository = Path(config["repository"])
    target = job["commit"]
    predecessor = job["predecessor"]
    not_before = datetime.fromisoformat(job["not_before"])
    if not_before.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria")
    if not check_only and datetime.now(timezone.utc) < not_before:
        raise RuntimeError("El horario autorizado aún no llegó")
    if run(["git", "remote", "get-url", "origin"], repository) != config["remote_url"]:
        raise RuntimeError("origin difiere del destino autorizado")
    if run(["git", "rev-parse", f"{target}^{{commit}}"], repository) != target:
        raise RuntimeError("El commit aprobado no coincide")
    parents = run(["git", "show", "-s", "--format=%P", target], repository)
    if parents != (predecessor or ""):
        raise RuntimeError("La cadena de commits aprobada no coincide")
    validate_snapshot(repository, target)
    gh = config["gh"]
    run([gh, "auth", "status"])
    if run([gh, "api", "user", "--jq", ".login"]) != config["account"]:
        raise RuntimeError("La cuenta GitHub activa no es la autorizada")
    metadata = json.loads(
        run(
            [
                gh,
                "repo",
                "view",
                config["github_repository"],
                "--json",
                "nameWithOwner,visibility",
            ]
        )
    )
    if (
        metadata.get("nameWithOwner") != config["github_repository"]
        or metadata.get("visibility") != "PUBLIC"
    ):
        raise RuntimeError("El repositorio público autorizado no coincide")
    current = remote_head(repository)
    if current == target:
        return {"status": "already-published", "commit": target}
    if current != predecessor:
        if check_only and current is None:
            return {"status": "validated-awaiting-predecessor", "commit": target}
        raise RuntimeError("main remoto cambió o falta la entrega anterior")
    if check_only:
        return {"status": "validated-no-push", "commit": target}
    run(
        ["git", "push", "--porcelain", "origin", f"{target}:refs/heads/main"],
        repository,
    )
    if remote_head(repository) != target:
        raise RuntimeError("No se pudo confirmar el commit remoto")
    return {"status": "published", "commit": target}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("job")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    config = json.loads(manifest.read_text(encoding="utf-8"))
    with (manifest.parent / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            result = publish(config, args.job, check_only=args.check_only)
            exit_code = 0
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result = {"status": "failed", "error": str(exc)}
            exit_code = 1
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        suffix = "validation" if args.check_only else "result"
        record = manifest.parent / f"job-{args.job}-{suffix}.json"
        temporary = record.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temporary.replace(record)
        print(json.dumps(result), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
