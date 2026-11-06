"""Prueba el wheel instalado en un venv nuevo, fuera del árbol fuente."""

import argparse
import subprocess
import tempfile
import venv
from pathlib import Path


def verify(directory: Path) -> None:
    wheels = list(directory.resolve().glob("revlogs-*.whl"))
    if len(wheels) != 1:
        raise ValueError("Se requiere exactamente un wheel de revlogs")
    with tempfile.TemporaryDirectory(prefix="revlogs-installed-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / "bin" / "python"
        cli = environment / "bin" / "revlogs"
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheels[0]),
            ],
            cwd=root,
            check=True,
            timeout=120,
        )
        subprocess.run(
            [str(cli), "--help"], cwd=root, check=True, capture_output=True, timeout=30
        )
        logs = root / "logs"
        logs.mkdir()
        (logs / "app.log").write_text("ERROR ERROR WARN\n", encoding="utf-8")
        for name in ("first.md", "second.md"):
            result = subprocess.run(
                [str(cli), str(logs), "--fail-on", "error", "-o", str(logs / name)],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
            )
            if (
                result.returncode != 1
                or "Errores: 2" not in result.stdout
                or "Advertencias: 1" not in result.stdout
            ):
                raise RuntimeError("El wheel instalado no conserva conteos/umbrales")
        subprocess.run(
            [str(python), "-m", "pip", "check"], cwd=root, check=True, timeout=30
        )
    print("Wheel instalado: CLI, conteos, reportes repetidos y dependencias OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    verify(args.directory)


if __name__ == "__main__":
    main()
