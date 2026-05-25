from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import commitr


class CliEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_editor = os.environ.get("EDITOR")

    def tearDown(self) -> None:
        if self._old_editor is None:
            os.environ.pop("EDITOR", None)
        else:
            os.environ["EDITOR"] = self._old_editor

    def test_edit_in_editor_returns_edited_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "editor.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import sys
                    from pathlib import Path

                    Path(sys.argv[-1]).write_text("fix: edited message\\n")
                    """
                )
            )
            os.environ["EDITOR"] = f"{sys.executable} {script}"

            self.assertEqual(commitr._edit_in_editor("feat: initial"), "fix: edited message")

    def test_edit_in_editor_raises_when_editor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "editor.py"
            script.write_text("raise SystemExit(7)\n")
            os.environ["EDITOR"] = f"{sys.executable} {script}"

            with self.assertRaises(RuntimeError):
                commitr._edit_in_editor("feat: initial")


if __name__ == "__main__":
    unittest.main()
