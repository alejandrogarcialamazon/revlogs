"""Diagnóstico de GitHub con comandos simulados, sin credenciales ni red."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.check_github_access import Check, CommandResult, command, inspect_access


class GithubAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.codex = self.root / "codex"
        self.opencode = self.root / "opencode"
        for directory in (self.codex, self.opencode):
            directory.mkdir()
            (directory / "AGENTS.md").write_text(
                "gh auth status; gh api user --jq .login", encoding="utf-8"
            )
        self.identity = "expected-user"
        self.profile = '{"name":"github","mode":"primary"}'
        self.fail_auth = False

    def runner(self, args: list[str]) -> CommandResult:
        if args[0] == "gh":
            if args[1] == "auth":
                return CommandResult(1 if self.fail_auth else 0, "PRIVATE_OUTPUT")
            return CommandResult(0, self.identity)
        if args[0] == "git":
            return CommandResult(0, "!/path/gh auth git-credential")
        return CommandResult(0, self.profile)

    def inspect(self, auth_only: bool = False) -> list[Check]:
        return inspect_access(
            account="expected-user",
            gh="gh",
            codex_home=self.codex,
            opencode_home=self.opencode,
            opencode="opencode",
            auth_only=auth_only,
            runner=self.runner,
        )

    def test_ready_without_disclosing_command_outputs(self) -> None:
        checks = self.inspect()
        self.assertEqual(len(checks), 6)
        self.assertTrue(all(check.ok for check in checks))
        self.assertNotIn("PRIVATE_OUTPUT", repr(checks))

    def test_wrong_account(self) -> None:
        self.identity = "other-user"
        self.assertFalse(self.inspect()[1].ok)

    def test_authentication_failure(self) -> None:
        self.fail_auth = True
        self.assertFalse(self.inspect()[0].ok)

    def test_global_override_takes_precedence(self) -> None:
        (self.codex / "AGENTS.override.md").write_text("other instructions")
        self.assertFalse(self.inspect()[3].ok)

    def test_empty_override_uses_base_instructions(self) -> None:
        (self.codex / "AGENTS.override.md").write_text("\n")
        self.assertTrue(self.inspect()[3].ok)

    def test_missing_rules(self) -> None:
        (self.opencode / "AGENTS.md").unlink()
        self.assertFalse(self.inspect()[4].ok)

    def test_invalid_profile_output(self) -> None:
        self.profile = "non-json"
        self.assertFalse(self.inspect()[5].ok)

    def test_disabled_profile(self) -> None:
        self.profile = json.dumps(
            {"name": "github", "mode": "primary", "disable": True}
        )
        self.assertFalse(self.inspect()[5].ok)

    def test_auth_only_does_not_require_local_clients(self) -> None:
        (self.codex / "AGENTS.md").unlink()
        checks = self.inspect(auth_only=True)
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(check.ok for check in checks))

    def test_invalid_account(self) -> None:
        with self.assertRaises(ValueError):
            inspect_access(
                account="--invalid",
                gh="gh",
                codex_home=self.codex,
                opencode_home=self.opencode,
                opencode="opencode",
                runner=self.runner,
            )

    def test_missing_executable(self) -> None:
        with patch(
            "tools.check_github_access.subprocess.run", side_effect=FileNotFoundError
        ):
            self.assertEqual(command(["missing"]).code, 2)

    def test_command_timeout(self) -> None:
        with patch(
            "tools.check_github_access.subprocess.run",
            side_effect=subprocess.TimeoutExpired("gh", 60),
        ):
            self.assertEqual(command(["gh"]).code, 2)
