"""Precedencia, tipos, rutas y ausencia de ejecución de configuración."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from revlogs.cli import main
from revlogs.configuration import load_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.config = self.root / "settings.toml"
        (self.root / "app.log").write_text("ERROR\n", encoding="utf-8")

    def write(self, text: str) -> Path:
        self.config.write_text(text, encoding="utf-8")
        return self.config

    def cli(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--config", str(self.config), *arguments])
        return code, output.getvalue()

    def test_relative_paths_and_output(self) -> None:
        self.write('[revlogs]\npaths=["app.log"]\noutput="result.md"')
        self.assertEqual(self.cli()[0], 0)
        self.assertTrue((self.root / "result.md").exists())

    def test_cli_scalars_override_config(self) -> None:
        self.write('[revlogs]\npaths=["app.log"]\nfail_on="error"')
        code, _ = self.cli("--fail-on", "warning", "-o", str(self.root / "out.md"))
        self.assertEqual(code, 1)

    def test_cli_lists_replace_instead_of_append(self) -> None:
        self.write('[revlogs]\npaths=["app.log"]\ninclude=["*.missing"]')
        self.assertEqual(
            self.cli("--include", "*.log", "-o", str(self.root / "out.md"))[0], 0
        )

    def test_cli_paths_replace_config_paths(self) -> None:
        self.write('[revlogs]\npaths=["missing.log"]')
        self.assertEqual(
            self.cli(str(self.root / "app.log"), "-o", str(self.root / "out.md"))[0], 0
        )

    def test_false_cli_overrides_true_config(self) -> None:
        self.write('[revlogs]\npaths=["app.log"]\nstrict=true\ninclude_reports=true')
        _, output = self.cli(
            "--no-strict", "--no-include-reports", "-o", str(self.root / "out.md")
        )
        self.assertIn("Estricto: False", output)

    def test_unknown_keys_are_rejected(self) -> None:
        self.write('[revlogs]\nunknown="secret-value"')
        with self.assertRaises(ValueError) as raised:
            load_config(self.config)
        self.assertNotIn("secret-value", str(raised.exception))

    def test_boolean_is_not_integer(self) -> None:
        self.write("[revlogs]\nmax_files=true")
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_list_requires_strings(self) -> None:
        self.write("[revlogs]\npaths=[123]")
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_invalid_toml_is_rejected(self) -> None:
        self.write("[revlogs\n")
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_oversized_file_is_rejected(self) -> None:
        self.write("#" + "x" * 65536)
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_version_and_choices_are_checked(self) -> None:
        for text in ("schema_version=2\n[revlogs]", '[revlogs]\nformat="other"'):
            self.write(text)
            with self.assertRaises(ValueError):
                load_config(self.config)

    def test_invalid_config_is_not_ignored(self) -> None:
        self.write('[revlogs]\nstrict="yes"')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.cli()
