from __future__ import annotations

import unittest

from commitr import doctor


class DoctorTests(unittest.TestCase):
    def test_reports_no_staged_changes(self) -> None:
        findings = doctor.analyze_staged_changes(diff="", files=[])

        self.assertEqual(findings[0].level, "error")
        self.assertEqual(findings[0].code, "no_staged_changes")

    def test_warns_when_only_lockfiles_are_staged(self) -> None:
        findings = doctor.analyze_staged_changes(
            diff="diff --git a/uv.lock b/uv.lock\n+package = []\n",
            files=["uv.lock"],
        )

        self.assertIn("lockfile_only", {finding.code for finding in findings})

    def test_warns_about_binary_and_large_diffs(self) -> None:
        findings = doctor.analyze_staged_changes(
            diff=(
                "diff --git a/image.png b/image.png\n"
                "Binary files a/image.png and b/image.png differ\n"
                + ("+" * 12100)
            ),
            files=["image.png", "src/app.py"],
            max_diff_chars=12000,
        )

        codes = {finding.code for finding in findings}
        self.assertIn("binary_diff", codes)
        self.assertIn("large_diff", codes)

    def test_overall_status_prefers_errors_over_warnings(self) -> None:
        findings = [
            doctor.Finding("warning", "large_diff", "Diff is large."),
            doctor.Finding("error", "no_model", "No model configured."),
        ]

        self.assertEqual(doctor.overall_status(findings), "error")


if __name__ == "__main__":
    unittest.main()
