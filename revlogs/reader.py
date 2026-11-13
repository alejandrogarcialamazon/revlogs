"""Descubrimiento de archivos y lectura incremental tolerante a codificación."""

import os
import stat
from collections.abc import Callable, Generator, Iterator, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from .limits import ResourceLimitError, ScanBudget, ScanLimits
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
    budget: ScanBudget | None = None,
) -> Generator[LogSource, None, None]:
    """Valida rutas y omite duplicados, archivos especiales y enlaces simbólicos.

    Se usa scandir sin materializar todo el contenido de un directorio. Los
    errores se notifican sin interrumpir las otras rutas.
    """
    seen: set[tuple[int, int]] = set()
    stats = stats if stats is not None else DiscoveryStats()
    budget = budget if budget is not None else ScanBudget(ScanLimits())
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

    def walk(
        path: Path, descend: bool, base: Path, depth: int = 0
    ) -> Iterator[LogSource]:
        try:
            budget.visit()
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
                        budget.admit_file()
                        yield source
            elif stat.S_ISDIR(info.st_mode):
                stats.directories += 1
                if not descend:
                    return
                if depth > budget.limits.max_depth:
                    on_issue(
                        Issue(
                            path,
                            "Límite de profundidad alcanzado",
                            code="resource_limit",
                        )
                    )
                    return
                with os.scandir(path) as entries:
                    for entry in entries:
                        child = Path(entry.path)
                        yield from walk(child, recursive, base, depth + 1)
            else:
                on_issue(Issue(path, "No es un archivo regular; omitido"))
        except ResourceLimitError:
            raise
        except OSError as exc:
            report(path, exc)

    for path in paths:
        expanded = path.expanduser().absolute()
        try:
            base = expanded if expanded.is_dir() else expanded.parent
        except OSError as exc:
            report(expanded, exc)
            continue
        try:
            yield from walk(expanded, True, base)
        except ResourceLimitError as exc:
            budget.stopped = True
            on_issue(Issue(expanded, str(exc), code="resource_limit"))
            return


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


def read_lines(
    path: Path | LogSource, *, budget: ScanBudget | None = None
) -> Iterator[tuple[int, str, bool]]:
    """Devuelve número, texto y uso de latin-1 por línea física.

    La decodificación por línea permite tolerar archivos con codificación mixta
    sin releerlos ni perder resultados ya contados. Los errores de E/S se
    propagan al analizador, que conserva los resultados parciales.
    """
    budget = budget if budget is not None else ScanBudget(ScanLimits())
    if isinstance(path, Path):
        with open_log(path) as source:
            yield from read_lines(source, budget=budget)
        return
    file_bytes = 0
    number = 0
    while True:
        limits = budget.limits
        size = (
            min(
                limits.max_line_bytes,
                max(0, limits.max_file_bytes - file_bytes),
                max(0, limits.max_total_bytes - budget.bytes_read),
            )
            + 1
        )
        raw = path.stream.readline(size)
        if not raw:
            return
        number += 1
        file_bytes += len(raw)
        budget.bytes_read += len(raw)
        if budget.bytes_read > limits.max_total_bytes:
            raise ResourceLimitError("Límite global de bytes alcanzado", stop_scan=True)
        if file_bytes > limits.max_file_bytes:
            raise ResourceLimitError("Límite de bytes por archivo alcanzado")
        if len(raw) > limits.max_line_bytes:
            raise ResourceLimitError(f"Línea {number}: supera el límite de bytes")
        fallback = False
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            fallback = True
        if number == 1:
            text = text.removeprefix("\ufeff")
        yield number, text.rstrip("\r\n"), fallback
