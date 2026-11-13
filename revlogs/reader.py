"""Descubrimiento de archivos y lectura incremental tolerante a codificación."""

import os
import stat
from collections.abc import Callable, Generator, Iterator, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from .models import REPORT_MARKER, DiscoveryStats, Issue
from .safe_io import LogSource, UnsafeLogError, open_log

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


def discover_sources(
    paths: Sequence[Path],
    *,
    recursive: bool,
    on_issue: Callable[[Issue], None],
    excluded: Sequence[Path] = (),
    include_patterns: Sequence[str] = (),
    exclude_patterns: Sequence[str] = (),
    skip_reports: bool = True,
    stats: DiscoveryStats | None = None,
) -> Generator[LogSource, None, None]:
    """Valida rutas y omite duplicados, archivos especiales y enlaces simbólicos.

    Se usa scandir sin materializar todo el contenido de un directorio. Los
    errores se notifican sin interrumpir las otras rutas.
    """
    seen: set[tuple[int, int]] = set()
    stats = stats if stats is not None else DiscoveryStats()
    excluded_paths = {path.resolve() for path in excluded}

    def report(path: Path, exc: OSError) -> None:
        code = (
            "unsafe_input"
            if isinstance(exc, UnsafeLogError)
            else "missing_path"
            if isinstance(exc, FileNotFoundError)
            else "io_error"
        )
        on_issue(Issue(path, str(exc), code=code))

    def matches(path: Path, base: Path, patterns: Sequence[str]) -> bool:
        relative = path.relative_to(base).as_posix()
        return any(
            fnmatchcase(path.name, pattern) or fnmatchcase(relative, pattern)
            for pattern in patterns
        )

    def walk(path: Path, descend: bool, base: Path) -> Iterator[LogSource]:
        try:
            if matches(path, base, exclude_patterns):
                stats.skipped += 1
                return
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                on_issue(Issue(path, "Enlace simbólico omitido", code="unsafe_input"))
                return
            resolved = path.resolve()
            if any(
                item == resolved or item in resolved.parents for item in excluded_paths
            ):
                stats.skipped += 1
                return
            if stat.S_ISREG(info.st_mode):
                if include_patterns and not matches(path, base, include_patterns):
                    stats.skipped += 1
                    return
                identity = (info.st_dev, info.st_ino)
                if identity not in seen:
                    if not os.access(path, os.R_OK):
                        raise PermissionError(f"Sin permiso de lectura: {path}")
                    with open_log(path, expected=info) as source:
                        if skip_reports:
                            prefix = source.stream.read(256)
                            source.stream.seek(0)
                            if prefix.startswith(
                                (
                                    REPORT_MARKER.encode(),
                                    "# Reporte de análisis de logs\n\nInicio: ".encode(),
                                )
                            ):
                                stats.skipped += 1
                                return
                        seen.add(identity)
                        yield source
            elif stat.S_ISDIR(info.st_mode):
                stats.directories += 1
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


def discover_files(
    paths: Sequence[Path],
    *,
    recursive: bool,
    on_issue: Callable[[Issue], None],
    excluded: Sequence[Path] = (),
    include_patterns: Sequence[str] = (),
    exclude_patterns: Sequence[str] = (),
    skip_reports: bool = True,
    stats: DiscoveryStats | None = None,
) -> Iterator[Path]:
    """API de rutas orientativa; el analizador utiliza discover_sources."""
    sources = discover_sources(
        paths,
        recursive=recursive,
        on_issue=on_issue,
        excluded=excluded,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        skip_reports=skip_reports,
        stats=stats,
    )
    try:
        for source in sources:
            source.stream.close()
            yield source.path
    finally:
        sources.close()


def read_lines(path: Path | LogSource) -> Iterator[tuple[int, str, bool]]:
    """Devuelve número, texto y uso de latin-1 por línea física.

    La decodificación por línea permite tolerar archivos con codificación mixta
    sin releerlos ni perder resultados ya contados. Los errores de E/S se
    propagan al analizador, que conserva los resultados parciales.
    """
    if isinstance(path, Path):
        with open_log(path) as source:
            yield from read_lines(source)
        return
    for number, raw in enumerate(path.stream, start=1):
        fallback = False
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            fallback = True
        if number == 1:
            text = text.removeprefix("\ufeff")
        yield number, text.rstrip("\r\n"), fallback
