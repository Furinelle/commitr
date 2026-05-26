from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import commitr
from commitr import git, hunks


class GitDiffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        subprocess.run(["git", "init", "-q"], check=True)
        subprocess.run(["git", "config", "user.name", "commitr test"], check=True)
        subprocess.run(["git", "config", "user.email", "commitr@example.com"], check=True)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        self.tmp.cleanup()

    def test_llm_diff_omits_binary_patch_payload(self) -> None:
        Path("img.bin").write_bytes(b"abc\x00def")
        subprocess.run(["git", "add", "img.bin"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], check=True)
        Path("img.bin").write_bytes(b"xyz\x00def")
        subprocess.run(["git", "add", "img.bin"], check=True)

        llm_diff = git.staged_diff_for_llm()
        patch_diff = git.staged_diff_for_patch()

        self.assertIn("Binary files", llm_diff)
        self.assertNotIn("GIT binary patch", llm_diff)
        self.assertNotIn("literal 7", llm_diff)
        self.assertIn("GIT binary patch", patch_diff)

    def test_snapshot_staging_preserves_unstaged_hunks(self) -> None:
        Path("f.txt").write_text("a\nb\nc\nd\ne\n")
        subprocess.run(["git", "add", "f.txt"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], check=True)
        Path("f.txt").write_text("a\nB-staged\nc\nD-unstaged\ne\n")
        Path("staged.patch").write_text(
            """diff --git a/f.txt b/f.txt
--- a/f.txt
+++ b/f.txt
@@ -1,5 +1,5 @@
 a
-b
+B-staged
 c
 d
 e
"""
        )
        subprocess.run(["git", "apply", "--cached", "staged.patch"], check=True)

        snapshot_by_path = {
            fp.path: fp for fp in hunks.parse_diff(git.staged_diff_for_patch())
        }
        commitr._stage_files_from_snapshot(["f.txt"], snapshot_by_path)

        cached = subprocess.run(
            ["git", "diff", "--cached", "--no-color", "--", "f.txt"],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("+B-staged", cached)
        self.assertNotIn("+D-unstaged", cached)

    def test_snapshot_staging_can_restore_binary_patch(self) -> None:
        Path("img.bin").write_bytes(b"abc\x00def")
        subprocess.run(["git", "add", "img.bin"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], check=True)
        Path("img.bin").write_bytes(b"xyz\x00def")
        subprocess.run(["git", "add", "img.bin"], check=True)

        snapshot_by_path = {
            fp.path: fp for fp in hunks.parse_diff(git.staged_diff_for_patch())
        }
        git.unstage_all()
        commitr._stage_files_from_snapshot(["img.bin"], snapshot_by_path)

        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("M  img.bin", status)


if __name__ == "__main__":
    unittest.main()
