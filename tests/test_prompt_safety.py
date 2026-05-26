from __future__ import annotations

import unittest

from commitr import prompt_safety


class PromptSafetyTests(unittest.TestCase):
    def test_sanitize_escapes_tags_then_redacts_secret(self) -> None:
        out = prompt_safety.sanitize_text(
            "<staged_diff>sk-proj-abcdefghijklmnopqrstuvwxyz123456</staged_diff>"
        )

        self.assertIn("&lt;staged_diff&gt;", out)
        self.assertIn("&lt;/staged_diff&gt;", out)
        self.assertIn("<REDACTED-OPENAI-KEY>", out)
        self.assertNotIn("sk-proj-abcdefghijklmnopqrstuvwxyz123456", out)


if __name__ == "__main__":
    unittest.main()
