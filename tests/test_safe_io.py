"""Pruebas de sustitución de entradas y vida útil de descriptores Linux."""

import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from contextlib import AbstractContextManager, closing
from pathlib import Path
from unittest.mock import patch

from revlogs.analyzer import LogAnalyzer
from revlogs.reader import discover_sources, read_lines
from revlogs.safe_io import LogSource, UnsafeLogError, open_log


class SafeIOTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root / "app.log"
        self.log.write_text("ERROR original\n", encoding="utf-8")
        self.other = self.root / "private.log"
        self.other.write_text("FATAL debe permanecer sin leer\n", encoding="utf-8")
        self.real_open = os.open

    def swap_open(self, action: Callable[[], None]) -> Callable[..., int]:
        changed = False

        def intercept(path: str, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal changed
            if path == self.log.name and not changed:
                changed = True
                action()
            # Los argumentos originales de os.open se conservan sin alterarlos.
            return self.real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        return intercept

    def test_symlink_substitution_is_rejected_before_read(self) -> None:
        expected = self.log.lstat()

        def swap() -> None:
            self.log.unlink()
            self.log.symlink_to(self.other)

        with patch("revlogs.safe_io.os.open", side_effect=self.swap_open(swap)):
            with self.assertRaises(UnsafeLogError):
                with open_log(self.log, expected):
                    self.fail("No debe abrirse para lectura")

    def test_different_regular_inode_is_rejected(self) -> None:
        expected = self.log.lstat()
        with patch(
            "revlogs.safe_io.os.open",
            side_effect=self.swap_open(lambda: os.replace(self.other, self.log)),
        ):
            with self.assertRaises(UnsafeLogError):
                with open_log(self.log, expected):
                    self.fail("No debe leerse el archivo sustituto")

    def test_scanner_rejects_replacement_before_header_read(self) -> None:
        def swapped(
            path: Path, expected: os.stat_result | None = None
        ) -> AbstractContextManager[LogSource]:
            os.replace(self.other, path)
            return open_log(path, expected)

        with patch("revlogs.reader.open_log", side_effect=swapped):
            result = LogAnalyzer().scan([self.log])
        self.assertEqual(result.files, [])
        self.assertTrue(result.operational_failed)
        self.assertEqual(result.issues[0].code, "unsafe_input")

    def test_fifo_substitution_is_rejected(self) -> None:
        code = """import os,sys
from pathlib import Path
from unittest.mock import patch
from revlogs.safe_io import open_log,UnsafeLogError
path=Path(sys.argv[1]); expected=path.lstat(); original=os.open; changed=False
def intercept(name, flags, **kwargs):
 global changed
 if name==path.name and not changed:
  changed=True; path.unlink(); os.mkfifo(path)
 return original(name, flags, **kwargs)
with patch('revlogs.safe_io.os.open',side_effect=intercept):
 try:
  with open_log(path,expected): sys.exit(2)
 except UnsafeLogError: sys.exit(0)
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(self.log)],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_parent_replaced_by_symlink_is_rejected(self) -> None:
        parent = self.root / "parent"
        parent.mkdir()
        path = parent / "app.log"
        path.write_text("ERROR original", encoding="utf-8")
        expected = path.lstat()

        def intercept(name: str, flags: int, **kwargs: int) -> int:
            if name == "parent":
                parent.rename(self.root / "retained")
                parent.symlink_to(self.root, target_is_directory=True)
            return self.real_open(name, flags, **kwargs)

        with patch("revlogs.safe_io.os.open", side_effect=intercept):
            with self.assertRaises(OSError):
                with open_log(path, expected):
                    self.fail("No debe seguir un componente simbólico")

    def test_header_and_lines_use_original_descriptor(self) -> None:
        with closing(
            discover_sources([self.log], recursive=False, on_issue=lambda issue: None)
        ) as sources:
            source = next(sources)
            self.log.rename(self.root / "original.log")
            self.log.write_text("FATAL sustituto\n", encoding="utf-8")
            self.assertEqual(list(read_lines(source)), [(1, "ERROR original", False)])
        self.assertTrue(source.stream.closed)

    def test_early_generator_close_releases_stream(self) -> None:
        sources = discover_sources(
            [self.log], recursive=False, on_issue=lambda issue: None
        )
        source = next(sources)
        sources.close()
        self.assertTrue(source.stream.closed)

    def test_failed_open_does_not_leak_descriptors(self) -> None:
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(20):
            expected = self.other.lstat()
            with self.assertRaises(UnsafeLogError):
                with open_log(self.log, expected):
                    self.fail("La identidad no coincide")
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_missing_procfs_fails_closed(self) -> None:
        def intercept(path: str, flags: int, **kwargs: int) -> int:
            if path.startswith("/proc/self/fd/"):
                raise FileNotFoundError("procfs no disponible")
            return self.real_open(path, flags, **kwargs)

        with patch("revlogs.safe_io.os.open", side_effect=intercept):
            with self.assertRaises(UnsafeLogError):
                list(read_lines(self.log))

    def test_direct_fifo_returns_without_blocking(self) -> None:
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        code = (
            "from pathlib import Path; from revlogs.reader import read_lines; "
            "import sys; list(read_lines(Path(sys.argv[1])))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, str(fifo)],
            capture_output=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_unsupported_platform_fails_closed(self) -> None:
        with patch("revlogs.safe_io.sys.platform", "unsupported"):
            with self.assertRaises(UnsafeLogError):
                list(read_lines(self.log))

    def test_stream_creation_failure_releases_descriptors(self) -> None:
        before = len(os.listdir("/proc/self/fd"))
        with patch("revlogs.safe_io.os.fdopen", side_effect=OSError("Fallo de stream")):
            with self.assertRaises(OSError):
                with open_log(self.log):
                    self.fail("El stream no pudo crearse")
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_symbolic_loop_is_reported_without_crashing(self) -> None:
        loop = self.root / "loop"
        loop.symlink_to("loop")
        result = LogAnalyzer().scan([loop])
        self.assertTrue(result.operational_failed)
        self.assertTrue(result.issues)
