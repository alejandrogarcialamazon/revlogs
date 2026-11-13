"""Checkpoints privados y atómicos de archivos sin comprimir, con exclusión mutua."""

import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Any

from .safe_io import LogSource


class Checkpoints:
    """Avanza solamente tras generar todos los reportes correctamente."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().absolute()
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.entries: dict[str, Any] = {}
        self.fd: int | None = None
        self.signature: str | None = None

    def __enter__(self) -> "Checkpoints":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.is_symlink():
                raise ValueError("El estado incremental no puede ser un enlace")
            if self.path.exists():
                with self.path.open("rb") as stream:
                    raw = stream.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError("Estado incremental demasiado grande")
                data = json.loads(raw)
                if (
                    not isinstance(data, dict)
                    or data.get("version") != 1
                    or not isinstance(data.get("files"), dict)
                ):
                    raise ValueError("Estado incremental inválido")
                self.entries = data["files"]
                self.signature = data.get("signature")
            return self
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def bind(self, signature: str) -> None:
        if self.entries and self.signature != signature:
            raise ValueError("Las reglas cambiaron; usar otro archivo --state")
        self.signature = signature

    def start(self, source: LogSource) -> tuple[int, int]:
        if source.compression != "none":
            raise ValueError("El modo incremental requiere archivos sin comprimir")
        info = os.fstat(source.stream.fileno())
        entry = self.entries.get(str(source.path.absolute()))
        if not isinstance(entry, dict):
            return 0, 0
        try:
            offset, lines = entry["offset"], entry["lines"]
            if (
                type(offset) is not int
                or type(lines) is not int
                or min(offset, lines) < 0
            ):
                raise ValueError("Checkpoint inválido")
            if [info.st_dev, info.st_ino] != entry["identity"] or info.st_size < offset:
                return 0, 0
            source.stream.seek(0)
            digest = hashlib.sha256(source.stream.read(min(offset, 4096))).hexdigest()
            if digest != entry["prefix"]:
                return 0, 0
            return offset, lines
        except (KeyError, TypeError) as exc:
            raise ValueError("Checkpoint inválido") from exc

    def record(self, source: LogSource, lines: int) -> None:
        offset = source.stream.tell()
        info = os.fstat(source.stream.fileno())
        source.stream.seek(0)
        digest = hashlib.sha256(source.stream.read(min(offset, 4096))).hexdigest()
        source.stream.seek(offset)
        self.entries[str(source.path.absolute())] = {
            "identity": [info.st_dev, info.st_ino],
            "offset": offset,
            "lines": lines,
            "prefix": digest,
        }

    def save(self) -> None:
        data = json.dumps(
            {"version": 1, "signature": self.signature, "files": self.entries},
            sort_keys=True,
        ).encode()
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("Estado incremental demasiado grande")
        fd, name = tempfile.mkstemp(prefix=".revlogs-state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
