"""Reglas de búsqueda configurables y acumulación acotada de evidencias."""

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .limits import ResourceLimitError, ScanBudget, ScanLimits
from .matching import (
    DEFAULT_ERROR_PATTERNS as DEFAULT_ERROR_PATTERNS,
)
from .matching import (
    DEFAULT_WARNING_PATTERNS as DEFAULT_WARNING_PATTERNS,
)
from .matching import (
    Counter,
    PatternMatcher,
    SearchError,
)
from .models import DiscoveryStats, Evidence, FileResult, Issue, ScanResult
from .parsers import LogParser, ParseError
from .reader import discover_sources, read_lines
from .safe_io import LogSource

LOGGER = logging.getLogger(__name__)


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
        limits: ScanLimits | None = None,
        error_literals: Sequence[str] = (),
        warning_literals: Sequence[str] = (),
        regex_timeout: float = 0.5,
        regex_memory_mib: int = 256,
        format: str = "text",
        level_fields: Sequence[str] = ("level", "severity", "log.level"),
        numeric_levels: str = "python",
    ) -> None:
        if max_details < 0 or max_excerpt_chars < 1:
            raise ValueError("Límites de evidencias inválidos")
        self.parser = LogParser(format, level_fields, numeric_levels)
        self.matcher = PatternMatcher(
            error_patterns,
            warning_patterns,
            error_literals=error_literals,
            warning_literals=warning_literals,
            timeout=regex_timeout,
            memory_mib=regex_memory_mib,
        )
        self.max_details = max_details
        self.max_excerpt_chars = max_excerpt_chars
        self.limits = limits or ScanLimits()

    def analyze_file(
        self,
        path: Path,
        result: ScanResult,
        *,
        source: LogSource | None = None,
        budget: ScanBudget | None = None,
        counter: Counter | None = None,
    ) -> FileResult:
        if counter is None:
            with self.matcher.session() as active_counter:
                return self.analyze_file(
                    path, result, source=source, budget=budget, counter=active_counter
                )
        file_result = FileResult(path)
        budget = budget if budget is not None else ScanBudget(self.limits)
        try:
            for number, line, fallback in read_lines(
                source if source is not None else path, budget=budget
            ):
                file_result.lines_read += 1
                file_result.fallback_lines += int(fallback)
                try:
                    parsed = self.parser.parse(line, counter)
                except ParseError as exc:
                    file_result.parse_errors += 1
                    result.add_issue(
                        Issue(path, f"Línea {number}: {exc}", code="parse_error"),
                        self.limits.max_issues,
                    )
                    continue
                file_result.structured_lines += int(parsed.format != "text")
                file_result.text_lines += int(parsed.format == "text")
                for severity, count in parsed.counts.items():
                    if not count:
                        continue
                    category = file_result.categories[severity]
                    category.occurrences += count
                    category.matching_lines += 1
                    if len(category.evidence) < self.max_details:
                        if budget.details >= self.limits.max_total_details:
                            result.details_limited = True
                            continue
                        excerpt = line[: self.max_excerpt_chars]
                        if len(line) > self.max_excerpt_chars:
                            excerpt += " … [truncado]"
                        category.evidence.append(Evidence(number, excerpt, count))
                        budget.details += 1
            file_result.complete = file_result.parse_errors == 0
        except OSError as exc:
            limited = isinstance(exc, ResourceLimitError)
            if isinstance(exc, ResourceLimitError) and exc.stop_scan:
                budget.stopped = True
            if isinstance(exc, SearchError):
                budget.stopped = True
            issue = Issue(
                path,
                str(exc),
                code=exc.code
                if isinstance(exc, SearchError)
                else "resource_limit"
                if limited
                else "io_error",
            )
            result.add_issue(issue, self.limits.max_issues)
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
        budget = ScanBudget(self.limits)

        def on_issue(issue: Issue) -> None:
            if optional_paths and issue.code == "missing_path":
                issue = replace(issue, blocking=False, code="optional_missing")
            result.add_issue(issue, self.limits.max_issues)
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
            budget=budget,
        )
        with self.matcher.session() as active_counter:
            try:
                for source in sources:
                    LOGGER.info("Analizando %s", source.path)
                    result.files.append(
                        self.analyze_file(
                            source.path,
                            result,
                            source=source,
                            budget=budget,
                            counter=active_counter,
                        )
                    )
                    if budget.stopped:
                        break
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
        result.bytes_read = budget.bytes_read
        return result
