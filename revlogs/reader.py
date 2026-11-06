"""Descubrimiento de archivos y lectura incremental tolerante a codificación."""

import os
import stat
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

from .models import Issue

DEFAULT_PATHS: tuple[Path, ...] = tuple(
    Path(path)
    for path in (
        "/var/log/syslog",
        "/var/log/messages",
        "/var/log/auth.log",
        "/var/log/kern.log",
        "/var/log/nginx/error.log",
        "/var/log/apache2/error.log",
    )
)


def discover_files(
    paths: Sequence[Path],
    *,
    recursive: bool,
    on_issue: Callable[[Issue], None],
    excluded: Sequence[Path] = (),
) -> Iterator[Path]:
    """Valida rutas y omite duplicados, archivos especiales y enlaces simbólicos.

    Se usa scandir sin materializar todo el contenido de un directorio. Los
    errores se notifican sin interrumpir las otras rutas.
    """
    seen: set[tuple[int, int]] = set()
    excluded_paths = {path.resolve() for path in excluded}

    def report(path: Path, exc: OSError) -> None:
        on_issue(Issue(path, str(exc)))

    def walk(path: Path, descend: bool) -> Iterator[Path]:
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                on_issue(Issue(path, "Enlace simbólico omitido"))
                return
            if stat.S_ISREG(info.st_mode):
                if path.resolve() in excluded_paths:
                    return
                identity = (info.st_dev, info.st_ino)
                if identity not in seen:
                    if not os.access(path, os.R_OK):
                        raise PermissionError(f"Sin permiso de lectura: {path}")
                    seen.add(identity)
                    yield path.absolute()
            elif stat.S_ISDIR(info.st_mode):
                if not descend:
                    return
                with os.scandir(path) as entries:
                    for entry in entries:
                        child = Path(entry.path)
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if recursive:
                                    yield from walk(child, True)
                            else:
                                yield from walk(child, False)
                        except OSError as exc:
                            report(child, exc)
            else:
                on_issue(Issue(path, "No es un archivo regular; omitido"))
        except OSError as exc:
            report(path, exc)

    for path in paths:
        yield from walk(path.expanduser(), True)


def read_lines(path: Path) -> Iterator[tuple[int, str, bool]]:
    """Devuelve número, texto y uso de latin-1 por línea física.

    La decodificación por línea permite tolerar archivos con codificación mixta
    sin releerlos ni perder resultados ya contados. Los errores de E/S se
    propagan al analizador, que conserva los resultados parciales.
    """
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, start=1):
            fallback = False
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
                fallback = True
            if number == 1:
                text = text.removeprefix("\ufeff")
            yield number, text.rstrip("\r\n"), fallback
