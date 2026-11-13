"""Exportadores de esquema v1; conteos separados de muestras e incidencias."""

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import asdict

from .models import (
    JSON_REPORT_PREFIX,
    FileResult,
    ScanResult,
    Severity,
)
from .reports import MarkdownRenderer, ReportRenderer


def summary(result: ScanResult) -> dict[str, int | bool]:
    return {
        "files": len(result.files),
        "lines_read": sum(f.lines_read for f in result.files),
        "errors": result.total(Severity.ERROR),
        "warnings": result.total(Severity.WARNING),
        "bytes_read": result.bytes_read,
        "operational_failed": result.operational_failed,
        "strict": result.strict,
        "issues": len(result.issues),
        "issues_omitted": result.issues_omitted,
        "omitted_blocking": result.omitted_blocking,
        "details_limited": result.details_limited,
    }


def file_record(file: FileResult) -> dict[str, object]:
    return {
        "path": str(file.path),
        "lines_read": file.lines_read,
        "complete": file.complete,
        "fallback_lines": file.fallback_lines,
        "structured_lines": file.structured_lines,
        "text_lines": file.text_lines,
        "parse_errors": file.parse_errors,
        "decode_issues": file.decode_issues,
        "encoding": file.encoding,
        "compression": file.compression,
        "categories": {
            severity.value: {
                "occurrences": category.occurrences,
                "matching_lines": category.matching_lines,
                "omitted_lines": category.matching_lines - len(category.evidence),
                "evidence": [asdict(evidence) for evidence in category.evidence],
            }
            for severity, category in file.categories.items()
        },
    }


class JsonRenderer:
    def render(self, result: ScanResult) -> Iterator[str]:
        encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False)
        yield JSON_REPORT_PREFIX
        header = {
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat()
            if result.finished_at
            else None,
            "summary": summary(result),
        }
        yield from encoder.iterencode(header)
        # La cabecera anterior se integra como objeto metadata para mantener streaming.
        yield ',"files":['
        for index, file in enumerate(result.files):
            if index:
                yield ","
            yield from encoder.iterencode(file_record(file))
        yield '],"issues":['
        for index, issue in enumerate(result.issues):
            if index:
                yield ","
            yield from encoder.iterencode(
                {
                    "path": str(issue.path),
                    "message": issue.message,
                    "code": issue.code,
                    "blocking": issue.blocking,
                }
            )
        yield "]}\n"


CSV_FIELDS = (
    "revlogs_report",
    "schema_version",
    "record_type",
    "path",
    "severity",
    "occurrences",
    "matching_lines",
    "omitted_lines",
    "line_number",
    "text",
    "metric",
    "value",
    "code",
    "blocking",
    "complete",
    "encoding",
    "compression",
    "lines_read",
)


def _cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = "".join(
        char if char.isprintable() or char in "\t\r\n" else f"\\u{ord(char):04x}"
        for char in value
    )
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def csv_records(result: ScanResult) -> Iterator[dict[str, object]]:
    for key, value in summary(result).items():
        yield {"record_type": "summary", "metric": key, "value": value}
    yield {
        "record_type": "metadata",
        "metric": "started_at",
        "value": result.started_at.isoformat(),
    }
    yield {
        "record_type": "metadata",
        "metric": "finished_at",
        "value": result.finished_at.isoformat() if result.finished_at else "",
    }
    for file in result.files:
        yield {
            "record_type": "file",
            "path": str(file.path),
            "complete": file.complete,
            "encoding": file.encoding,
            "compression": file.compression,
            "lines_read": file.lines_read,
        }
        for severity, category in file.categories.items():
            yield {
                "record_type": "category",
                "path": str(file.path),
                "severity": severity.value,
                "occurrences": category.occurrences,
                "matching_lines": category.matching_lines,
                "omitted_lines": category.matching_lines - len(category.evidence),
            }
            for evidence in category.evidence:
                yield {
                    "record_type": "evidence",
                    "path": str(file.path),
                    "severity": severity.value,
                    "line_number": evidence.line_number,
                    "occurrences": evidence.occurrences,
                    "text": evidence.text,
                }
    for issue in result.issues:
        yield {
            "record_type": "issue",
            "path": str(issue.path),
            "text": issue.message,
            "code": issue.code,
            "blocking": issue.blocking,
        }


class CsvRenderer:
    def render(self, result: ScanResult) -> Iterator[str]:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\r\n")
        writer.writeheader()
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for record in csv_records(result):
            writer.writerow(
                {
                    "revlogs_report": "revlogs",
                    "schema_version": 1,
                    **{key: _cell(value) for key, value in record.items()},
                }
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)


RENDERERS: dict[str, type[ReportRenderer]] = {
    "markdown": MarkdownRenderer,
    "json": JsonRenderer,
    "csv": CsvRenderer,
}
