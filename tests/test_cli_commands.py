from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

import commitr


class CliCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self._old_cwd = os.getcwd()
        self._old_env = os.environ.copy()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        subprocess.run(["git", "init", "-q"], check=True)
        subprocess.run(["git", "config", "user.name", "commitr test"], check=True)
        subprocess.run(["git", "config", "user.email", "commitr@example.com"], check=True)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        os.environ.clear()
        os.environ.update(self._old_env)
        self.tmp.cleanup()

    def test_style_command_prints_profile_from_history(self) -> None:
        Path("app.py").write_text("print('hello')\n")
        subprocess.run(["git", "add", "app.py"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(cli): add greeting"], check=True)

        result = self.runner.invoke(commitr.app, ["style"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Language: English", result.output)
        self.assertIn("Types: feat", result.output)
        self.assertIn("Scopes: cli", result.output)

    def test_doctor_command_reports_no_staged_changes_as_error(self) -> None:
        os.environ["COMMITR_MODEL"] = "test/model"

        result = self.runner.invoke(commitr.app, ["doctor"])

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("no_staged_changes", result.output)

    def test_doctor_command_warns_for_lockfile_only_commit(self) -> None:
        os.environ["COMMITR_MODEL"] = "test/model"
        Path("uv.lock").write_text("version = 1\n")
        subprocess.run(["git", "add", "uv.lock"], check=True)

        result = self.runner.invoke(commitr.app, ["doctor"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("lockfile_only", result.output)


if __name__ == "__main__":
    unittest.main()
