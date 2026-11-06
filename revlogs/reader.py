"""Descubrimiento de archivos y lectura incremental tolerante a codificación."""

import os
import stat
from collections.abc import Callable, Iterator, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from .models import REPORT_MARKER, Issue

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
    include_patterns: Sequence[str] = (),
    exclude_patterns: Sequence[str] = (),
    skip_reports: bool = True,
) -> Iterator[Path]:
    """Valida rutas y omite duplicados, archivos especiales y enlaces simbólicos.

    Se usa scandir sin materializar todo el contenido de un directorio. Los
    errores se notifican sin interrumpir las otras rutas.
    """
    seen: set[tuple[int, int]] = set()
    excluded_paths = {path.resolve() for path in excluded}

    def report(path: Path, exc: OSError) -> None:
        on_issue(Issue(path, str(exc)))

    def matches(path: Path, base: Path, patterns: Sequence[str]) -> bool:
        relative = path.relative_to(base).as_posix()
        return any(
            fnmatchcase(path.name, pattern) or fnmatchcase(relative, pattern)
            for pattern in patterns
        )

    def walk(path: Path, descend: bool, base: Path) -> Iterator[Path]:
        try:
            resolved = path.resolve()
            if any(
                item == resolved or item in resolved.parents for item in excluded_paths
            ):
                return
            if matches(path, base, exclude_patterns):
                return
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                on_issue(Issue(path, "Enlace simbólico omitido"))
                return
            if stat.S_ISREG(info.st_mode):
                if include_patterns and not matches(path, base, include_patterns):
                    return
                identity = (info.st_dev, info.st_ino)
                if identity not in seen:
                    if not os.access(path, os.R_OK):
                        raise PermissionError(f"Sin permiso de lectura: {path}")
                    if skip_reports:
                        with path.open("rb") as stream:
                            prefix = stream.read(256)
                        if prefix.startswith(
                            (
                                REPORT_MARKER.encode(),
                                "# Reporte de análisis de logs\n\nInicio: ".encode(),
                            )
                        ):
                            return
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
                                    yield from walk(child, True, base)
                            else:
                                yield from walk(child, False, base)
                        except OSError as exc:
                            report(child, exc)
            else:
                on_issue(Issue(path, "No es un archivo regular; omitido"))
        except OSError as exc:
            report(path, exc)

    for path in paths:
        expanded = path.expanduser().absolute()
        try:
            base = expanded if expanded.is_dir() else expanded.parent
        except OSError as exc:
            report(expanded, exc)
            continue
        yield from walk(expanded, True, base)


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
