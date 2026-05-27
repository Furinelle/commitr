from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from commitr import prompt_safety


class PromptSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        prompt_safety.collect_and_clear_findings()

    def tearDown(self) -> None:
        prompt_safety.collect_and_clear_findings()

    def test_sanitize_escapes_tags_then_redacts_secret(self) -> None:
        out = prompt_safety.sanitize_text(
            "<staged_diff>sk-proj-abcdefghijklmnopqrstuvwxyz123456</staged_diff>"
        )

        self.assertIn("&lt;staged_diff&gt;", out)
        self.assertIn("&lt;/staged_diff&gt;", out)
        self.assertIn("<REDACTED-OPENAI-KEY>", out)
        self.assertNotIn("sk-proj-abcdefghijklmnopqrstuvwxyz123456", out)

    def test_findings_cleared_after_collect(self) -> None:
        prompt_safety.sanitize_text("sk-proj-abcdefghijklmnopqrstuvwxyz123456")
        first = prompt_safety.collect_and_clear_findings()
        second = prompt_safety.collect_and_clear_findings()

        self.assertEqual(first, [("openai_key", 1)])
        self.assertEqual(second, [])

    def test_findings_isolated_across_threads(self) -> None:
        """Each thread's top-level Context is independent — buffers don't leak."""
        def worker(secret: str) -> list[tuple[str, int]]:
            # Fresh thread → fresh ContextVar default → fresh buffer.
            prompt_safety.sanitize_text(secret)
            return prompt_safety.collect_and_clear_findings()

        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = [
                ex.submit(worker, "sk-proj-abcdefghijklmnopqrstuvwxyz111111"),
                ex.submit(worker, "AKIA1234567890ABCDEF and AKIA9999999999ABCDEF"),
            ]
            results = [f.result() for f in futures]

        self.assertEqual(results[0], [("openai_key", 1)])
        self.assertEqual(results[1], [("aws_access_key", 2)])
        # Main thread's buffer was never touched.
        self.assertEqual(prompt_safety.collect_and_clear_findings(), [])


if __name__ == "__main__":
    unittest.main()
