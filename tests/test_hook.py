from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from commitr import hook


class HookTests(unittest.TestCase):
    def test_fill_message_file_prepends_generated_message_to_empty_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            msg_file = Path(tmp) / "COMMIT_EDITMSG"
            msg_file.write_text("# Please enter the commit message\n# Changes to be committed:\n")

            wrote = hook.fill_message_file(str(msg_file), "feat: add hook mode")

            self.assertTrue(wrote)
            self.assertTrue(msg_file.read_text().startswith("feat: add hook mode\n\n#"))

    def test_fill_message_file_does_not_overwrite_user_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            msg_file = Path(tmp) / "COMMIT_EDITMSG"
            msg_file.write_text("docs: keep user message\n\n# Please enter the commit message\n")

            wrote = hook.fill_message_file(str(msg_file), "feat: generated")

            self.assertFalse(wrote)
            self.assertEqual(
                msg_file.read_text(),
                "docs: keep user message\n\n# Please enter the commit message\n",
            )


if __name__ == "__main__":
    unittest.main()
