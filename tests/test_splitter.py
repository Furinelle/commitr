from __future__ import annotations

import unittest

from commitr import splitter


class SplitterTests(unittest.TestCase):
    def test_parse_json_accepts_fenced_json(self) -> None:
        parsed = splitter._parse_json(
            '```json\n{"groups": [{"message": "feat: x", "files": ["a.py"]}]}\n```'
        )

        self.assertEqual(
            parsed,
            {"groups": [{"message": "feat: x", "files": ["a.py"]}]},
        )

    def test_parse_json_extracts_first_object_from_extra_text(self) -> None:
        parsed = splitter._parse_json(
            'Sure:\n{"groups": [{"message": "fix: x", "files": ["b.py"]}]}\nDone'
        )

        self.assertEqual(parsed["groups"][0]["files"], ["b.py"])


if __name__ == "__main__":
    unittest.main()
