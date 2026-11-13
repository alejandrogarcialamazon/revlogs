"""Integridad de artefactos y manifiestos de distribución."""

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.release_checksums import checksum, main, manifest


class ReleaseTests(unittest.TestCase):
    def test_streaming_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.whl"
            data = b"synthetic" * 300000
            path.write_bytes(data)
            self.assertEqual(checksum(path), hashlib.sha256(data).hexdigest())

    def test_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                manifest(Path(temp))

    def test_manifest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wheel = root / "revlogs-1.1.0.whl"
            wheel.write_bytes(b"wheel")
            (root / "revlogs-1.1.0.tar.gz").write_bytes(b"sdist")
            with contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys, "argv", ["checksums", temp]):
                    self.assertEqual(main(), 0)
                with patch.object(sys, "argv", ["checksums", temp, "--verify"]):
                    self.assertEqual(main(), 0)
                    wheel.write_bytes(b"tampered")
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as caught:
                            main()
                    self.assertEqual(caught.exception.code, 2)

    def test_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source").write_bytes(b"fake")
            (root / "package.whl").symlink_to(root / "source")
            (root / "package.tar.gz").write_bytes(b"fake")
            with self.assertRaises(ValueError):
                manifest(root)
