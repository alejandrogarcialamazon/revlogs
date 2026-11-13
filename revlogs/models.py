"""Modelos compartidos entre descubrimiento, análisis y presentación."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

REPORT_MARKER = "<!-- revlogs:report v1 -->"


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
    structured_lines: int = 0
    text_lines: int = 0
    parse_errors: int = 0
    decode_issues: int = 0
    encoding: str = "auto"
    compression: str = "none"
    categories: dict[Severity, CategoryResult] = field(
        default_factory=lambda: {severity: CategoryResult() for severity in Severity}
    )


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str
    blocking: bool = True
    code: str = "io_error"


@dataclass
class DiscoveryStats:
    directories: int = 0
    skipped: int = 0


@dataclass
class ScanResult:
    started_at: datetime
    finished_at: datetime | None = None
    files: list[FileResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    strict: bool = False
    bytes_read: int = 0
    issues_omitted: int = 0
    omitted_blocking: bool = False
    details_limited: bool = False

    def add_issue(self, issue: Issue, maximum: int = 1000) -> None:
        if len(self.issues) < maximum:
            self.issues.append(issue)
        else:
            self.issues_omitted += 1
            self.omitted_blocking |= issue.blocking

    @property
    def operational_failed(self) -> bool:
        return (
            not self.files
            or self.omitted_blocking
            or (self.strict and self.issues_omitted > 0)
            or any(i.blocking or self.strict for i in self.issues)
        )

    def total(self, severity: Severity) -> int:
        return sum(item.categories[severity].occurrences for item in self.files)
