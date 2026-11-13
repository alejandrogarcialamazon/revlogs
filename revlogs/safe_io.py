"""Apertura de logs Linux sin seguir enlaces ni abrir dispositivos para lectura."""

import errno
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class UnsafeLogError(OSError):
    """La identidad o el tipo del archivo no cumplen la política de lectura."""


@dataclass(frozen=True)
class LogSource:
    path: Path
    stream: "BinaryStream"
    compression: str = "none"


class BinaryStream(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...
    def readline(self, size: int = -1, /) -> bytes: ...
    def seek(self, offset: int, whence: int = 0, /) -> int: ...
    def tell(self) -> int: ...
    def close(self) -> None: ...
    @property
    def closed(self) -> bool: ...
    def __iter__(self) -> Iterator[bytes]: ...


def _validate(info: os.stat_result, expected: os.stat_result, path: Path) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise UnsafeLogError(
            errno.EINVAL, "La entrada no es un archivo regular", str(path)
        )
    if (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino):
        raise UnsafeLogError(
            errno.ESTALE, "El archivo cambió desde su descubrimiento", str(path)
        )


@contextmanager
def open_log(path: Path, expected: os.stat_result | None = None) -> Iterator[LogSource]:
    """Abre por identidad y conserva el descriptor para cabecera y lectura.

    O_PATH permite validar tipo/inodo sin abrir FIFO o dispositivos para lectura.
    Cada componente de la ruta del usuario se abre con O_NOFOLLOW. El paso de
    O_PATH a lectura usa únicamente /proc/self/fd del propio proceso y se vuelve
    a validar con fstat. Sin Linux/procfs se falla de forma cerrada.
    """
    if not sys.platform.startswith("linux") or not getattr(os, "O_PATH", 0):
        raise UnsafeLogError(errno.ENOTSUP, "Se requiere Linux con O_PATH", str(path))
    absolute = path.expanduser().absolute()
    expected = expected if expected is not None else absolute.lstat()
    _validate(expected, expected, absolute)
    directory: int | None = None
    probe: int | None = None
    reader: int | None = None
    try:
        directory_flags = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directory = os.open("/", directory_flags)
        for component in absolute.parts[1:-1]:
            next_directory = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        probe = os.open(
            absolute.name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory
        )
        _validate(os.fstat(probe), expected, absolute)
        try:
            reader = os.open(
                f"/proc/self/fd/{probe}", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
            )
        except OSError as exc:
            raise UnsafeLogError(
                exc.errno or errno.EIO,
                "No se pudo leer el descriptor validado",
                str(path),
            ) from exc
        _validate(os.fstat(reader), expected, absolute)
        stream = os.fdopen(reader, "rb")
        reader = None  # La propiedad del descriptor pasa al stream.
        with stream:
            yield LogSource(absolute, stream)
    finally:
        for descriptor in (reader, probe, directory):
            if descriptor is not None:
                os.close(descriptor)
