"""Severidad estructurada sin falsos positivos por el mensaje."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.models import ScanResult, Severity


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / "app.log"

    def scan(self, text: str, format: str = "json", **options: object) -> ScanResult:
        self.path.write_text(text, encoding="utf-8")
        return LogAnalyzer(format=format, **options).scan([self.path])  # type: ignore[arg-type]

    def test_json_info_ignores_error_words_in_message(self) -> None:
        result = self.scan(json.dumps({"level": "INFO", "message": "ERROR FATAL WARN"}))
        self.assertEqual(result.total(Severity.ERROR), 0)
        self.assertEqual(result.total(Severity.WARNING), 0)

    def test_json_event_is_counted_once(self) -> None:
        result = self.scan('{"level":"ERROR","message":"ERROR ERROR WARNING"}')
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 0)

    def test_warning_alias_and_case(self) -> None:
        self.assertEqual(self.scan('{"severity":"wArN"}').total(Severity.WARNING), 1)

    def test_nested_level_field(self) -> None:
        self.assertEqual(
            self.scan('{"log":{"level":"critical"}}').total(Severity.ERROR), 1
        )

    def test_custom_level_field(self) -> None:
        result = self.scan(
            '{"event":{"priority":"warning"}}', level_fields=("event.priority",)
        )
        self.assertEqual(result.total(Severity.WARNING), 1)

    def test_missing_level_is_not_guessed_from_message(self) -> None:
        result = self.scan('{"message":"ERROR"}')
        self.assertEqual(result.total(Severity.ERROR), 0)
        self.assertEqual(result.issues[0].code, "parse_error")

    def test_malformed_json_does_not_stop_later_events(self) -> None:
        result = self.scan('{"level":"ERROR"}\n{bad\n{"level":"WARN"}\n')
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 1)
        self.assertEqual(result.files[0].parse_errors, 1)
        self.assertFalse(result.files[0].complete)

    def test_duplicate_keys_are_rejected(self) -> None:
        self.assertTrue(
            self.scan('{"level":"INFO","level":"ERROR"}').operational_failed
        )

    def test_conflicting_levels_are_rejected(self) -> None:
        self.assertTrue(
            self.scan('{"level":"INFO","severity":"ERROR"}').operational_failed
        )

    def test_numeric_python_levels(self) -> None:
        result = self.scan('{"level":30}\n{"level":40}\n{"level":20}\n')
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 1)

    def test_numeric_syslog_levels(self) -> None:
        result = self.scan(
            '{"level":3}\n{"level":4}\n{"level":6}', numeric_levels="syslog"
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 1)

    def test_invalid_level_types_and_arrays(self) -> None:
        for text in ('{"level":true}', '{"level":null}', '{"level":"unknown"}', "[]"):
            self.assertTrue(self.scan(text).operational_failed)

    def test_syslog_pri_controls_classification(self) -> None:
        result = self.scan(
            "<11>Nov 13 host app: INFO\n<12>1 - host app - - - ERROR\n<14>message ERROR FATAL WARN",
            format="syslog",
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 1)
        self.assertEqual(result.files[0].structured_lines, 3)

    def test_auto_mixes_text_and_structured_without_silent_fallback(self) -> None:
        result = self.scan(
            '{"level":"INFO","message":"ERROR"}\n<11>event\nWARNING text\n{bad\n<999>ERROR',
            format="auto",
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.total(Severity.WARNING), 1)
        self.assertEqual(result.files[0].parse_errors, 2)

    def test_cli_structured_threshold_and_conflicting_options(self) -> None:
        self.path.write_text('{"level":"ERROR"}', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(
                [
                    str(self.path),
                    "--format",
                    "json",
                    "--fail-on",
                    "error",
                    "-o",
                    str(self.root / "report.md"),
                ]
            )
        self.assertEqual(code, 1)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([str(self.path), "--format", "json", "--error-pattern", "oops"])
