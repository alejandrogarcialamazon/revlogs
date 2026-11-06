"""Modelos compartidos entre descubrimiento, análisis y presentación."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class Evidence:
    line_number: int
    text: str
    occurrences: int


@dataclass
class CategoryResult:
    occurrences: int = 0
    matching_lines: int = 0
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class FileResult:
    path: Path
    lines_read: int = 0
    fallback_lines: int = 0
    complete: bool = False
    categories: dict[Severity, CategoryResult] = field(
        default_factory=lambda: {severity: CategoryResult() for severity in Severity}
    )


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


@dataclass
class ScanResult:
    started_at: datetime
    finished_at: datetime | None = None
    files: list[FileResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def total(self, severity: Severity) -> int:
        return sum(item.categories[severity].occurrences for item in self.files)
