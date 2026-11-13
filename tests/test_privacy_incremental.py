"""Pruebas de redacción y checkpoints con logs exclusivamente sintéticos."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from revlogs.analyzer import LogAnalyzer
from revlogs.cli import main
from revlogs.incremental import Checkpoints
from revlogs.models import Severity
from revlogs.redaction import Redactor


class PrivacyTests(unittest.TestCase):
    def test_builtin_redaction(self) -> None:
        redactor = Redactor(True)
        for text, secret in [
            ('ERROR password="private value"', "private value"),
            ("WARN token=abc123", "abc123"),
            ('{"level":"ERROR","api_key":"hello"}', "hello"),
            ("ERROR Authorization: Bearer aBc.123", "aBc.123"),
            ("WARN https://user:pass@example.com/x", "user:pass"),
            ("ERROR user@example.com", "user@example.com"),
        ]:
            with self.subTest(text=text):
                self.assertNotIn(secret, redactor.apply(text))

    def test_optional_and_literals(self) -> None:
        self.assertEqual(Redactor().apply("password=abc"), "password=abc")
        self.assertNotIn("private", Redactor(literals=["private"]).apply("private"))
        with self.assertRaises(ValueError):
            Redactor(literals=[""])

    def test_counts_before_redaction_and_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.log"
            path.write_text("ERROR token=ERRORVERYSECRET WARNING\n")
            result = LogAnalyzer(redact=True, max_excerpt_chars=24).scan([path])
            self.assertEqual(result.total(Severity.ERROR), 1)
            evidence = result.files[0].categories[Severity.ERROR].evidence[0].text
            self.assertNotIn("ERRORVERY", evidence)


class IncrementalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "input.log"
        self.state = self.root / "state.json"

    def scan(self) -> tuple[int, list[int]]:
        with Checkpoints(self.state) as state:
            result = LogAnalyzer(checkpoints=state).scan([self.log])
            self.assertFalse(result.operational_failed)
            state.save()
            return result.total(Severity.ERROR), [
                e.line_number
                for e in result.files[0].categories[Severity.ERROR].evidence
            ]

    def test_append_and_no_duplicates(self) -> None:
        self.log.write_text("ERROR first\n")
        self.assertEqual(self.scan(), (1, [1]))
        self.assertEqual(self.scan(), (0, []))
        with self.log.open("a") as stream:
            stream.write("ERROR second\n")
        self.assertEqual(self.scan(), (1, [2]))
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("ERROR", self.state.read_text())

    def test_partial_line_waits(self) -> None:
        self.log.write_text("ERROR first\nERROR par")
        self.assertEqual(self.scan(), (1, [1]))
        self.assertEqual(self.scan(), (0, []))
        with self.log.open("a") as stream:
            stream.write("tial\n")
        self.assertEqual(self.scan(), (1, [2]))

    def test_rotation(self) -> None:
        self.log.write_text("ERROR old\n")
        self.scan()
        self.log.rename(self.root / "old.log")
        self.log.write_text("ERROR new\n")
        self.assertEqual(self.scan(), (1, [1]))

    def test_truncation_and_rewrite(self) -> None:
        self.log.write_text("ERROR long old message\n")
        self.scan()
        self.log.write_text("ERROR new\n")
        self.assertEqual(self.scan(), (1, [1]))
        self.log.write_text("ERROR abc\n")
        self.assertEqual(self.scan(), (1, [1]))

    def test_corrupt_state_and_lock(self) -> None:
        self.state.write_text("{broken")
        with self.assertRaises(ValueError):
            with Checkpoints(self.state):
                pass
        self.state.unlink()
        with Checkpoints(self.state):
            with self.assertRaises(BlockingIOError):
                with Checkpoints(self.state):
                    pass

    def test_failed_output_does_not_advance(self) -> None:
        self.log.write_text("ERROR first\n")
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(
                [
                    str(self.log),
                    "--state",
                    str(self.state),
                    "-o",
                    str(self.root / "x.md"),
                ]
            )
        self.assertEqual(code, 0)
        checkpoint = json.loads(self.state.read_text())
        self.assertEqual(next(iter(checkpoint["files"].values()))["offset"], 12)
