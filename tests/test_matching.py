"""Regresiones de literales, regex aisladas y terminación de workers."""

import multiprocessing
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from revlogs.analyzer import LogAnalyzer
from revlogs.models import Severity


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / "app.log"

    def log(self, text: str) -> Path:
        self.path.write_text(text, encoding="utf-8")
        return self.path

    def test_literals_preserve_metacharacters(self) -> None:
        result = LogAnalyzer(error_literals=("a+b",)).scan(
            [self.log("a+b a+b\naaab\n")]
        )
        self.assertEqual(result.total(Severity.ERROR), 2)

    def test_literals_do_not_start_worker(self) -> None:
        with patch(
            "revlogs.matching.RegexWorker", side_effect=AssertionError("No worker")
        ):
            result = LogAnalyzer(warning_literals=("[deprecated]",)).scan(
                [self.log("[DEPRECATED] WARNING")]
            )
        self.assertEqual(result.total(Severity.WARNING), 2)

    def test_duplicate_literals_do_not_duplicate_counts(self) -> None:
        result = LogAnalyzer(error_literals=("a+b", "a+b")).scan([self.log("a+b")])
        self.assertEqual(result.total(Severity.ERROR), 1)

    def test_custom_regex_runs_and_closes_worker(self) -> None:
        before = {child.pid for child in multiprocessing.active_children()}
        result = LogAnalyzer(error_patterns=(r"a+b",)).scan([self.log("aaab aaab")])
        self.assertEqual(result.total(Severity.ERROR), 2)
        self.assertEqual(
            {child.pid for child in multiprocessing.active_children()}, before
        )

    def test_catastrophic_regex_times_out_and_keeps_previous_counts(self) -> None:
        before = {child.pid for child in multiprocessing.active_children()}
        result = LogAnalyzer(
            error_patterns=(r"ERROR|(a+)+$",), regex_timeout=0.05
        ).scan([self.log("ERROR\n" + "a" * 10000 + "!\n")])
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertFalse(result.files[0].complete)
        self.assertEqual(result.issues[0].code, "regex_timeout")
        self.assertEqual(
            {child.pid for child in multiprocessing.active_children()}, before
        )

    def test_cli_timeout_is_bounded_and_reports_failure(self) -> None:
        path = self.log("a" * 10000 + "!")
        report = self.root / "report.md"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "revlogs",
                str(path),
                "--error-pattern",
                "(a+)+$",
                "--regex-timeout",
                "0.05",
                "-o",
                str(report),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("fallido", report.read_text(encoding="utf-8"))

    def test_invalid_regex_is_rejected_before_scan(self) -> None:
        with self.assertRaises(re.error):
            LogAnalyzer(error_patterns=("[",))

    def test_oversized_pattern_is_rejected_without_worker(self) -> None:
        with patch(
            "revlogs.matching.RegexWorker", side_effect=AssertionError("No worker")
        ):
            with self.assertRaises(ValueError):
                LogAnalyzer(error_patterns=("a" * 4097,))

    def test_invalid_timeout_and_memory_are_rejected(self) -> None:
        builders: tuple[Callable[[], LogAnalyzer], ...] = (
            lambda: LogAnalyzer(regex_timeout=0.0),
            lambda: LogAnalyzer(regex_timeout=float("nan")),
            lambda: LogAnalyzer(regex_memory_mib=32),
        )
        for build in builders:
            with self.assertRaises(ValueError):
                build()

    def test_empty_literal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LogAnalyzer(error_literals=("",))
