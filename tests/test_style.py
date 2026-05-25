from __future__ import annotations

import unittest

from commitr import style


class StyleInferenceTests(unittest.TestCase):
    def test_infer_style_profile_from_conventional_english_history(self) -> None:
        profile = style.infer_profile(
            subjects=[
                "feat(cli): add dry-run option",
                "fix(config): preserve env override",
                "docs: update quick start",
                "feat(cli): add hook installer",
            ],
            samples=[
                "feat(cli): add dry-run option\n\nPrint generated messages without committing.",
                "fix(config): preserve env override",
            ],
        )

        self.assertEqual(profile.language, "English")
        self.assertTrue(profile.uses_conventional_commits)
        self.assertEqual(profile.types[:3], ["feat", "fix", "docs"])
        self.assertEqual(profile.scopes[:2], ["cli", "config"])
        self.assertEqual(profile.body_usage, "occasional")
        self.assertFalse(profile.uses_emoji_prefix)

    def test_infer_style_profile_detects_chinese_and_emoji_prefixes(self) -> None:
        profile = style.infer_profile(
            subjects=[
                "✨ feat(core): 增加记忆压缩",
                "🐛 fix(ui): 修复按钮状态",
                "📝 docs: 更新说明",
            ],
            samples=["✨ feat(core): 增加记忆压缩"],
        )

        self.assertEqual(profile.language, "Chinese")
        self.assertTrue(profile.uses_emoji_prefix)
        self.assertEqual(profile.types[:3], ["feat", "fix", "docs"])

    def test_render_profile_summary_is_stable_for_empty_history(self) -> None:
        profile = style.infer_profile(subjects=[], samples=[])

        summary = style.render_profile(profile)

        self.assertIn("Language: unknown", summary)
        self.assertIn("Conventional commits: no", summary)


if __name__ == "__main__":
    unittest.main()
