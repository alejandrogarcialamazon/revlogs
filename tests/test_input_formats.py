"""Lectura gzip, encodings y fallos sin perder límites ni seguridad."""

import codecs
import gzip
import tempfile
import unittest
from pathlib import Path

from revlogs.analyzer import LogAnalyzer
from revlogs.input_formats import ReadOptions
from revlogs.limits import ScanLimits
from revlogs.models import ScanResult, Severity
from revlogs.reports import MarkdownRenderer, write_report


class InputFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def scan(
        self,
        data: bytes,
        name: str = "app.log",
        *,
        options: ReadOptions | None = None,
        limits: ScanLimits | None = None,
    ) -> ScanResult:
        path = self.root / name
        path.write_bytes(data)
        return LogAnalyzer(read_options=options, limits=limits).scan([path])

    def test_gzip_suffix_streaming(self) -> None:
        result = self.scan(gzip.compress(b"ERROR WARN\n"), "app.log.gz")
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.files[0].compression, "gzip")

    def test_gzip_magic_without_suffix(self) -> None:
        self.assertEqual(self.scan(gzip.compress(b"ERROR\n")).total(Severity.ERROR), 1)

    def test_concatenated_gzip_members(self) -> None:
        result = self.scan(gzip.compress(b"ERROR\n") + gzip.compress(b"WARN\n"))
        self.assertEqual(result.total(Severity.WARNING), 1)

    def test_invalid_gzip_suffix_is_not_plain_text(self) -> None:
        result = self.scan(b"ERROR\n", "broken.gz")
        self.assertTrue(result.operational_failed)
        self.assertEqual(result.issues[0].code, "compression_error")

    def test_truncated_gzip_is_reported(self) -> None:
        self.assertTrue(self.scan(gzip.compress(b"ERROR\n")[:-5]).operational_failed)

    def test_gzip_crc_error_is_reported(self) -> None:
        data = bytearray(gzip.compress(b"ERROR\n"))
        data[-8] ^= 1
        self.assertTrue(self.scan(bytes(data)).operational_failed)

    def test_decompressed_line_limit_is_enforced(self) -> None:
        result = self.scan(
            gzip.compress(b"x" * 100000), limits=ScanLimits(max_line_bytes=32)
        )
        self.assertTrue(result.operational_failed)
        self.assertEqual(result.issues[0].code, "resource_limit")

    def test_compressed_byte_limit_is_enforced(self) -> None:
        result = self.scan(
            gzip.compress(b"ERROR\n"), limits=ScanLimits(max_compressed_bytes=5)
        )
        self.assertTrue(result.operational_failed)
        self.assertEqual(result.issues[0].code, "resource_limit")

    def test_utf16_and_utf32_boms(self) -> None:
        for encoding in ("utf-16", "utf-32"):
            result = self.scan("ERROR\nWARN\n".encode(encoding))
            self.assertEqual(result.total(Severity.ERROR), 1)
            self.assertEqual(result.total(Severity.WARNING), 1)

    def test_big_endian_and_false_newline_bytes(self) -> None:
        for encoding, bom in (
            ("utf-16-be", codecs.BOM_UTF16_BE),
            ("utf-32-be", codecs.BOM_UTF32_BE),
            ("utf-16-le", codecs.BOM_UTF16_LE),
        ):
            result = self.scan(bom + "ERROR Ċ਀\nWARN\n".encode(encoding))
            self.assertEqual(result.total(Severity.ERROR), 1)
            self.assertEqual(result.files[0].lines_read, 2)

    def test_explicit_endian_without_bom(self) -> None:
        result = self.scan(
            "ERROR\n".encode("utf-16-le"), options=ReadOptions(encoding="utf-16-le")
        )
        self.assertEqual(result.total(Severity.ERROR), 1)

    def test_explicit_utf16_requires_bom(self) -> None:
        result = self.scan(b"ERROR", options=ReadOptions(encoding="utf-16"))
        self.assertEqual(result.issues[0].code, "decode_error")

        result = self.scan(
            "\x00ERROR\n".encode("utf-16"), options=ReadOptions(encoding="utf-16")
        )
        self.assertEqual(result.total(Severity.ERROR), 1)

    def test_explicit_cp1252(self) -> None:
        result = self.scan(
            "ERROR €\n".encode("cp1252"), options=ReadOptions(encoding="cp1252")
        )
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.files[0].fallback_lines, 0)

    def test_strict_decode_failure_preserves_counts(self) -> None:
        result = self.scan(b"ERROR\nWARN \xff\n", options=ReadOptions(encoding="utf-8"))
        self.assertEqual(result.total(Severity.ERROR), 1)
        self.assertEqual(result.issues[0].code, "decode_error")
        self.assertFalse(result.files[0].complete)

    def test_replace_and_ignore_are_explicit_advice(self) -> None:
        for policy in ("replace", "ignore"):
            result = self.scan(
                b"ERROR \xff\n", options=ReadOptions(encoding="utf-8", errors=policy)
            )
            self.assertEqual(result.files[0].decode_issues, 1)
            self.assertFalse(result.operational_failed)
            self.assertFalse(result.issues[0].blocking)

    def test_gzip_report_is_excluded_after_decompression(self) -> None:
        path = self.root / "source.log"
        path.write_text("ERROR", encoding="utf-8")
        result = LogAnalyzer().scan([path])
        report = self.root / "report.md"
        write_report(report, result, MarkdownRenderer())
        (self.root / "report.gz").write_bytes(gzip.compress(report.read_bytes()))
        self.assertEqual(LogAnalyzer().scan([self.root]).total(Severity.ERROR), 1)

    def test_gzip_json_integrates_structured_parser(self) -> None:
        path = self.root / "events.gz"
        path.write_bytes(
            gzip.compress(b'{"level":"INFO","message":"ERROR"}\n{"level":"WARN"}\n')
        )
        result = LogAnalyzer(format="json").scan([path])
        self.assertEqual(result.total(Severity.ERROR), 0)
        self.assertEqual(result.total(Severity.WARNING), 1)

    def test_invalid_encoding_is_rejected(self) -> None:
        for encoding in ("unknown-codec", "unicode-escape"):
            with self.assertRaises(ValueError):
                ReadOptions(encoding=encoding)
