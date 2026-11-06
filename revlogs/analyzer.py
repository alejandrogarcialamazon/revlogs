"""Reglas de búsqueda configurables y acumulación acotada de evidencias."""

import logging
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from re import Pattern

from .models import Evidence, FileResult, Issue, ScanResult, Severity
from .reader import discover_files, read_lines

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

    def analyze_file(self, path: Path, result: ScanResult) -> FileResult:
        file_result = FileResult(path)
        try:
            for number, line, fallback in read_lines(path):
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
    ) -> ScanResult:
        result = ScanResult(started_at=datetime.now().astimezone())

        def on_issue(issue: Issue) -> None:
            result.issues.append(issue)
            LOGGER.warning("%s: %s", issue.path, issue.message)

        for path in discover_files(
            paths, recursive=recursive, on_issue=on_issue, excluded=excluded
        ):
            LOGGER.info("Analizando %s", path)
            result.files.append(self.analyze_file(path, result))
        result.finished_at = datetime.now().astimezone()
        return result
