from __future__ import annotations

import unittest

from commitr import issue


class IssueBranchDetectionTests(unittest.TestCase):
    def test_detects_number_in_feature_branch(self) -> None:
        self.assertEqual(issue.detect_issue_from_branch("feat/123-add-thing"), 123)

    def test_detects_number_after_issue_prefix(self) -> None:
        self.assertEqual(issue.detect_issue_from_branch("fix-issue-42-crash"), 42)

    def test_detects_number_with_gh_prefix(self) -> None:
        self.assertEqual(issue.detect_issue_from_branch("gh-777"), 777)

    def test_detects_pure_issue_branch(self) -> None:
        self.assertEqual(issue.detect_issue_from_branch("issue/9000"), 9000)

    def test_ignores_branch_without_number(self) -> None:
        self.assertIsNone(issue.detect_issue_from_branch("master"))
        self.assertIsNone(issue.detect_issue_from_branch("dev"))

    def test_handles_empty_branch(self) -> None:
        self.assertIsNone(issue.detect_issue_from_branch(""))
        self.assertIsNone(issue.detect_issue_from_branch(None))


class IssueFormatContextTests(unittest.TestCase):
    def test_format_includes_title_and_body(self) -> None:
        out = issue._format_context({
            "number": 42,
            "title": "Crash on empty input",
            "body": "Reproduces every time.",
            "labels": [{"name": "bug"}, {"name": "p1"}],
            "state": "OPEN",
        })

        self.assertIn("Issue #42: Crash on empty input", out)
        self.assertIn("Labels: bug, p1", out)
        self.assertIn("Reproduces every time.", out)
        self.assertNotIn("State:", out)  # open is default, skip

    def test_format_truncates_long_bodies(self) -> None:
        big = "x" * 2000
        out = issue._format_context({
            "number": 1, "title": "t", "body": big, "labels": [], "state": "open",
        })

        self.assertIn("…", out)
        self.assertLess(len(out), 1500)

    def test_format_shows_non_open_state(self) -> None:
        out = issue._format_context({
            "number": 5, "title": "t", "body": "", "labels": [], "state": "closed",
        })

        self.assertIn("State: closed", out)


if __name__ == "__main__":
    unittest.main()
