"""Publicaciones verificadas con remotos Git locales, sin tocar GitHub."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tools import scheduled_push


class ScheduledPushTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "work"
        self.remote = self.root / "remote.git"
        self.repository.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        subprocess.run(
            ["git", "init", "--bare", str(self.remote)],
            check=True,
            capture_output=True,
        )
        self.git("remote", "add", "origin", str(self.remote))
        self.first = self.commit("first")
        self.second = self.commit("second")
        self.config: dict[str, Any] = {
            "repository": str(self.repository),
            "remote_url": str(self.remote),
            "gh": "/fake/gh",
            "account": "approved-user",
            "github_repository": "approved-user/revlogs",
            "jobs": {
                "1": {
                    "commit": self.first,
                    "predecessor": None,
                    "not_before": "2000-01-01T00:00:00+00:00",
                },
                "2": {
                    "commit": self.second,
                    "predecessor": self.first,
                    "not_before": "2000-01-01T00:00:00+00:00",
                },
            },
        }
        self.real_run = scheduled_push.run
        mock = patch("tools.scheduled_push.run", side_effect=self.command)
        mock.start()
        self.addCleanup(mock.stop)
        validate = patch("tools.scheduled_push.validate_snapshot")
        self.validation = validate.start()
        self.addCleanup(validate.stop)

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repository,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def commit(self, text: str) -> str:
        (self.repository / "file.txt").write_text(text, encoding="utf-8")
        self.git("add", "file.txt")
        self.git("commit", "-m", text)
        return self.git("rev-parse", "HEAD")

    def command(self, args: list[str], cwd: Path | None = None) -> str:
        if args[0] == "/fake/gh":
            if args[1] == "api":
                return "approved-user"
            if args[1] == "repo":
                return '{"nameWithOwner":"approved-user/revlogs","visibility":"PUBLIC"}'
            return "authenticated"
        return self.real_run(args, cwd)

    def test_first_push_does_not_publish_later_head(self) -> None:
        result = scheduled_push.publish(self.config, "1")
        self.assertEqual(result["status"], "published")
        self.assertEqual(scheduled_push.remote_head(self.repository), self.first)

    def test_second_push_and_idempotent_retry(self) -> None:
        scheduled_push.publish(self.config, "1")
        scheduled_push.publish(self.config, "2")
        result = scheduled_push.publish(self.config, "2")
        self.assertEqual(result["status"], "already-published")
        self.assertEqual(scheduled_push.remote_head(self.repository), self.second)

    def test_second_waits_for_first(self) -> None:
        with self.assertRaises(RuntimeError):
            scheduled_push.publish(self.config, "2")
        self.assertIsNone(scheduled_push.remote_head(self.repository))

    def test_check_only_does_not_publish(self) -> None:
        scheduled_push.publish(self.config, "1", check_only=True)
        result = scheduled_push.publish(self.config, "2", check_only=True)
        self.assertEqual(result["status"], "validated-awaiting-predecessor")
        self.assertIsNone(scheduled_push.remote_head(self.repository))

    def test_changed_origin_is_rejected(self) -> None:
        self.config["remote_url"] = "other"
        with self.assertRaises(RuntimeError):
            scheduled_push.publish(self.config, "1")

    def test_changed_parent_is_rejected(self) -> None:
        self.config["jobs"]["2"]["predecessor"] = None
        with self.assertRaises(RuntimeError):
            scheduled_push.publish(self.config, "2")

    def test_remote_advance_is_not_overwritten(self) -> None:
        scheduled_push.publish(self.config, "1")
        third = self.commit("unexpected")
        self.git("push", "origin", f"{third}:refs/heads/main")
        with self.assertRaises(RuntimeError):
            scheduled_push.publish(self.config, "2")
        self.assertEqual(scheduled_push.remote_head(self.repository), third)

    def test_early_publication_is_rejected(self) -> None:
        self.config["jobs"]["1"]["not_before"] = "2100-01-01T00:00:00+00:00"
        with self.assertRaises(RuntimeError):
            scheduled_push.publish(self.config, "1")
        self.assertIsNone(scheduled_push.remote_head(self.repository))

    def test_wrong_account_is_rejected(self) -> None:
        self.config["account"] = "other"
        with self.assertRaises(RuntimeError):
            scheduled_push.publish(self.config, "1")
        self.assertIsNone(scheduled_push.remote_head(self.repository))
