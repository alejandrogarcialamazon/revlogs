"""Genera o verifica SHA-256 de wheel y sdist, sin dependencias externas."""

import argparse
import hashlib
import hmac
from pathlib import Path


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest(directory: Path) -> str:
    packages = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
    if not any(p.suffix == ".whl" for p in packages) or not any(
        p.name.endswith(".tar.gz") for p in packages
    ):
        raise ValueError("Se requieren wheel y sdist")
    if any(p.is_symlink() for p in packages):
        raise ValueError("No se admiten enlaces simbólicos")
    return "".join(f"{checksum(path)}  {path.name}\n" for path in packages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        expected = manifest(args.directory)
        target = args.directory / "SHA256SUMS"
        if args.verify:
            if not hmac.compare_digest(target.read_text(encoding="utf-8"), expected):
                raise ValueError("Los paquetes no coinciden con SHA256SUMS")
        else:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(expected)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print("SHA256SUMS verificado" if args.verify else "SHA256SUMS generado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
