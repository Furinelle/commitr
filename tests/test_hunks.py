from __future__ import annotations

import unittest

from commitr import hunks


SAMPLE_DIFF = """\
diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1,3 +1,4 @@
 def f():
-    return 1
+    return 2
+    # changed
@@ -10,2 +11,3 @@
 def g():
     pass
+    # added
diff --git a/b.txt b/b.txt
index 3333333..4444444 100644
--- a/b.txt
+++ b/b.txt
@@ -1 +1 @@
-hello
+world
"""


BINARY_DIFF = """\
diff --git a/img.png b/img.png
index 1111..2222 100644
Binary files a/img.png and b/img.png differ
"""


RENAME_DIFF = """\
diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
"""


class ParseDiffTests(unittest.TestCase):
    def test_parses_two_files_and_three_hunks(self) -> None:
        files = hunks.parse_diff(SAMPLE_DIFF)

        self.assertEqual([f.path for f in files], ["a.py", "b.txt"])
        self.assertEqual(len(files[0].hunks), 2)
        self.assertEqual(len(files[1].hunks), 1)
        self.assertFalse(files[0].atomic)
        self.assertFalse(files[1].atomic)

    def test_hunk_headers_are_extracted(self) -> None:
        files = hunks.parse_diff(SAMPLE_DIFF)

        self.assertEqual(files[0].hunks[0].old_start, 1)
        self.assertEqual(files[0].hunks[1].old_start, 10)

    def test_binary_diff_is_atomic(self) -> None:
        files = hunks.parse_diff(BINARY_DIFF)

        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].atomic)

    def test_rename_is_atomic(self) -> None:
        files = hunks.parse_diff(RENAME_DIFF)

        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].atomic)

    def test_empty_diff_returns_empty_list(self) -> None:
        self.assertEqual(hunks.parse_diff(""), [])
        self.assertEqual(hunks.parse_diff("   \n"), [])


class SummarizeTests(unittest.TestCase):
    def test_summary_lists_each_hunk_with_id(self) -> None:
        files = hunks.parse_diff(SAMPLE_DIFF)

        out = hunks.summarize_for_llm(files)

        self.assertIn("Hunk a.py#0", out)
        self.assertIn("Hunk a.py#1", out)
        self.assertIn("Hunk b.txt#0", out)

    def test_atomic_files_get_marker(self) -> None:
        files = hunks.parse_diff(BINARY_DIFF)

        out = hunks.summarize_for_llm(files)

        self.assertIn("atomic", out)


class AnalyzeHunkSplitsTests(unittest.TestCase):
    def test_analyze_hunk_splits_redacts_and_wraps_untrusted_hunks(self) -> None:
        calls: list[dict] = []
        original_completion = hunks.litellm.completion
        files = hunks.parse_diff(
            """diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@
 print("x")
+TOKEN = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"
"""
        )

        class _Message:
            content = '{"groups":[{"message":"fix: x","hunks":["a.py#0"]}]}'

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return _Response()

        hunks.litellm.completion = fake_completion
        try:
            hunks.analyze_hunk_splits(
                file_patches=files,
                subjects=["feat: <subject>"],
                samples=["fix: <sample>"],
                model="test/model",
            )
        finally:
            hunks.litellm.completion = original_completion

        sent = calls[0]["messages"][1]["content"]
        self.assertIn("<hunks>", sent)
        self.assertIn("</hunks>", sent)
        self.assertIn("<REDACTED-OPENAI-KEY>", sent)
        self.assertNotIn("sk-proj-abcdefghijklmnopqrstuvwxyz123456", sent)
        self.assertIn("&lt;subject&gt;", sent)
        self.assertIn("untrusted input", hunks.HUNK_SPLIT_SYSTEM_PROMPT)


class GroupResponseTests(unittest.TestCase):
    def test_parse_groups_resolves_hunk_ids(self) -> None:
        files = hunks.parse_diff(SAMPLE_DIFF)
        raw = """
        {
          "groups": [
            {"message": "feat: change return", "hunks": ["a.py#0"], "rationale": "r1"},
            {"message": "chore: greeting", "hunks": ["b.txt#0", "a.py#1"], "rationale": "r2"}
          ]
        }
        """

        groups = hunks.parse_groups_response(raw, files)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].message, "feat: change return")
        self.assertEqual([r.path for r in groups[1].refs], ["b.txt", "a.py"])

    def test_missing_hunks_go_into_catchall(self) -> None:
        files = hunks.parse_diff(SAMPLE_DIFF)
        raw = '{"groups": [{"message": "x", "hunks": ["a.py#0"]}]}'

        groups = hunks.parse_groups_response(raw, files)

        all_refs = [(r.path, r.index) for g in groups for r in g.refs]
        self.assertIn(("a.py", 1), all_refs)
        self.assertIn(("b.txt", 0), all_refs)


class RenderPatchTests(unittest.TestCase):
    def test_render_emits_only_selected_hunks(self) -> None:
        files = hunks.parse_diff(SAMPLE_DIFF)
        group = hunks.HunkGroup(
            message="x",
            refs=[hunks.HunkRef(path="a.py", index=0)],
        )

        patch = hunks.render_patch_for_group(group, files)

        self.assertIn("diff --git a/a.py b/a.py", patch)
        self.assertIn("@@ -1,3 +1,4 @@", patch)
        self.assertNotIn("@@ -10,2 +11,3 @@", patch)
        self.assertNotIn("b.txt", patch)

    def test_render_atomic_file_emits_all_hunks(self) -> None:
        files = hunks.parse_diff(BINARY_DIFF)
        group = hunks.HunkGroup(
            message="x",
            refs=[hunks.HunkRef(path="img.png", index=0)],
        )

        patch = hunks.render_patch_for_group(group, files)

        self.assertIn("Binary files", patch)


if __name__ == "__main__":
    unittest.main()
