"""Prueba el wheel instalado en un venv nuevo, fuera del árbol fuente."""

import argparse
import csv
import gzip
import json
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
        regex_log = root / "regex.log"
        regex_log.write_text("ERROR\n" + "a" * 10000 + "!\n", encoding="utf-8")
        regex_report = root / "regex.md"
        timed = subprocess.run(
            [
                str(cli),
                str(regex_log),
                "--error-pattern",
                "(a+)+$",
                "--regex-timeout",
                "0.05",
                "-o",
                str(regex_report),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=8,
        )
        if timed.returncode != 2 or "regex_timeout" not in regex_report.read_text(
            encoding="utf-8"
        ).replace("\\_", "_"):
            raise RuntimeError("El wheel instalado no controla el timeout de regex")
        compressed = root / "events.gz"
        compressed.write_bytes(
            gzip.compress(
                '{"level":"INFO","message":"ERROR"}\n{"level":"WARN"}\n'.encode(
                    "utf-16"
                )
            )
        )
        structured = subprocess.run(
            [
                str(cli),
                str(compressed),
                "--format",
                "json",
                "--encoding",
                "utf-16",
                "-o",
                str(root / "structured.md"),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=15,
        )
        if (
            structured.returncode != 0
            or "Errores: 0" not in structured.stdout
            or "Advertencias: 1" not in structured.stdout
        ):
            raise RuntimeError("El wheel instalado no integra gzip, UTF-16 y JSON")
        configuration = root / "settings.toml"
        configuration.write_text(
            '[revlogs]\npaths=["logs/app.log"]\nreport_format="json"\noutput="export.json"\ncsv_output="export.csv"',
            encoding="utf-8",
        )
        subprocess.run(
            [str(cli), "--config", str(configuration)],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=15,
        )
        exported = json.loads((root / "export.json").read_text(encoding="utf-8"))
        if exported["metadata"]["summary"]["errors"] != 2:
            raise RuntimeError("JSON instalado inconsistente")
        with (root / "export.csv").open(encoding="utf-8", newline="") as stream:
            metrics = {
                row["metric"]: row["value"]
                for row in csv.DictReader(stream)
                if row["record_type"] == "summary"
            }
        if int(metrics["errors"]) != 2:
            raise RuntimeError("CSV instalado inconsistente")
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
