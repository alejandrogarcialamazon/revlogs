"""Reglas de búsqueda configurables y acumulación acotada de evidencias."""

import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from re import Pattern

from .models import DiscoveryStats, Evidence, FileResult, Issue, ScanResult, Severity
from .reader import discover_sources, read_lines
from .safe_io import LogSource

LOGGER = logging.getLogger(__name__)
DEFAULT_ERROR_PATTERNS = (r"\b(?:ERROR|CRITICAL|FATAL)\b",)
DEFAULT_WARNING_PATTERNS = (r"\b(?:WARNING|WARN)\b",)


class LogAnalyzer:
    """Cuenta coincidencias no superpuestas de cada categoría, sin distinguir caso.

    Una línea puede pertenecer a ambas categorías. Alternativas repetidas en
    una misma categoría no duplican una coincidencia en la misma posición.
    """

    def __init__(
        self,
        *,
        error_patterns: Sequence[str] = DEFAULT_ERROR_PATTERNS,
        warning_patterns: Sequence[str] = DEFAULT_WARNING_PATTERNS,
        max_details: int = 50,
        max_excerpt_chars: int = 1000,
    ) -> None:
        if max_details < 0 or max_excerpt_chars < 1:
            raise ValueError("Límites de evidencias inválidos")
        self.rules = {
            Severity.ERROR: self._compile(error_patterns),
            Severity.WARNING: self._compile(warning_patterns),
        }
        self.max_details = max_details
        self.max_excerpt_chars = max_excerpt_chars

    @staticmethod
    def _compile(patterns: Sequence[str]) -> Pattern[str]:
        if not patterns:
            raise ValueError("Se requiere al menos un patrón por categoría")
        compiled = re.compile(
            "|".join(f"(?:{pattern})" for pattern in patterns), re.IGNORECASE
        )
        if compiled.search(""):
            raise ValueError("Los patrones no deben coincidir con texto vacío")
        return compiled

    def analyze_file(
        self, path: Path, result: ScanResult, *, source: LogSource | None = None
    ) -> FileResult:
        file_result = FileResult(path)
        try:
            for number, line, fallback in read_lines(
                source if source is not None else path
            ):
                file_result.lines_read += 1
                file_result.fallback_lines += int(fallback)
                for severity, rule in self.rules.items():
                    count = sum(
                        1
                        for match in rule.finditer(line)
                        if match.end() > match.start()
                    )
                    if not count:
                        continue
                    category = file_result.categories[severity]
                    category.occurrences += count
                    category.matching_lines += 1
                    if len(category.evidence) < self.max_details:
                        excerpt = line[: self.max_excerpt_chars]
                        if len(line) > self.max_excerpt_chars:
                            excerpt += " … [truncado]"
                        category.evidence.append(Evidence(number, excerpt, count))
            file_result.complete = True
        except OSError as exc:
            issue = Issue(path, str(exc))
            result.issues.append(issue)
            LOGGER.warning("Lectura incompleta de %s: %s", path, exc)
        if file_result.fallback_lines:
            LOGGER.warning(
                "%s: %d líneas decodificadas con latin-1",
                path,
                file_result.fallback_lines,
            )
        return file_result

    def scan(
        self,
        paths: Sequence[Path],
        *,
        recursive: bool = False,
        excluded: Sequence[Path] = (),
        include_patterns: Sequence[str] = (),
        exclude_patterns: Sequence[str] = (),
        skip_reports: bool = True,
        optional_paths: bool = False,
        strict: bool = False,
    ) -> ScanResult:
        result = ScanResult(started_at=datetime.now().astimezone(), strict=strict)
        stats = DiscoveryStats()

        def on_issue(issue: Issue) -> None:
            if optional_paths and issue.code == "missing_path":
                issue = replace(issue, blocking=False, code="optional_missing")
            result.issues.append(issue)
            LOGGER.warning("%s: %s", issue.path, issue.message)

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
                LOGGER.info("Analizando %s", source.path)
                result.files.append(
                    self.analyze_file(source.path, result, source=source)
                )
        finally:
            sources.close()
        if not result.files:
            if stats.skipped:
                code, message = (
                    "empty_selection",
                    "Sin archivos elegibles tras aplicar filtros",
                )
            elif stats.directories:
                code, message = "empty_directory", "Directorio sin archivos analizables"
            else:
                code, message = "no_readable_inputs", "No hay entradas legibles"
            on_issue(Issue(paths[0] if paths else Path("."), message, code=code))
        result.finished_at = datetime.now().astimezone()
        return result
