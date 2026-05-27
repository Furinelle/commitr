from __future__ import annotations

import io
import unittest
import warnings
from unittest import mock

from rich.console import Console

import commitr
from commitr import git, hunks, prompt_safety, splitter
from commitr.redact import redact_secrets


class RedactSecretsTests(unittest.TestCase):
    def _assert_single_redaction(
        self,
        text: str,
        kind: str,
        replacement: str,
    ) -> None:
        redacted, findings = redact_secrets(text)

        self.assertIn(replacement, redacted)
        self.assertEqual([(f.kind, f.count) for f in findings], [(kind, 1)])

    def test_redacts_openai_key(self) -> None:
        self._assert_single_redaction(
            "key=sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            "openai_key",
            "<REDACTED-OPENAI-KEY>",
        )

    def test_redacts_aws_access_key(self) -> None:
        self._assert_single_redaction(
            "aws AKIA1234567890ABCDEF ready",
            "aws_access_key",
            "<REDACTED-AWS-ACCESS-KEY>",
        )

    def test_redacts_jwt(self) -> None:
        self._assert_single_redaction(
            "jwt eyJaaaaaaaa.bbbbbbbbb.ccccccccc",
            "jwt",
            "<REDACTED-JWT>",
        )

    def test_redacts_anthropic_key(self) -> None:
        self._assert_single_redaction(
            "anthropic sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
            "anthropic_key",
            "<REDACTED-ANTHROPIC-KEY>",
        )

    def test_redacts_github_pat(self) -> None:
        self._assert_single_redaction(
            "github ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ",
            "github_pat",
            "<REDACTED-GITHUB-PAT>",
        )

    def test_redacts_slack_token(self) -> None:
        self._assert_single_redaction(
            "slack xoxb-1234567890-abcdef",
            "slack_token",
            "<REDACTED-SLACK-TOKEN>",
        )

    def test_redacts_private_key_header(self) -> None:
        # Header alone (no END marker) still trips the fallback pattern.
        self._assert_single_redaction(
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "private_key_header",
            "<REDACTED-PRIVATE-KEY>",
        )

    def test_redacts_private_key_block_entire_pem(self) -> None:
        pem = (
            "before\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy\n"
            "-----END RSA PRIVATE KEY-----\n"
            "after"
        )
        redacted, findings = redact_secrets(pem)

        self.assertIn("<REDACTED-PRIVATE-KEY-BLOCK>", redacted)
        self.assertNotIn("MIIEowIBAAK", redacted)
        self.assertNotIn("-----BEGIN", redacted)
        self.assertNotIn("-----END", redacted)
        self.assertTrue(redacted.startswith("before\n"))
        self.assertTrue(redacted.endswith("after"))
        self.assertEqual(
            [(f.kind, f.count) for f in findings],
            [("private_key_block", 1)],
        )

    def test_redacts_private_key_header_when_end_missing(self) -> None:
        # Truncated PEM (header only) falls through to the header-only pattern.
        redacted, findings = redact_secrets(
            "-----BEGIN ENCRYPTED PRIVATE KEY-----\nMIIEowIBAAK..."
        )

        self.assertIn("<REDACTED-PRIVATE-KEY>", redacted)
        self.assertEqual(
            [(f.kind, f.count) for f in findings],
            [("private_key_header", 1)],
        )

    def test_redacts_aws_iam_role_prefix(self) -> None:
        self._assert_single_redaction(
            "role AROA1234567890ABCDEF active",
            "aws_access_key",
            "<REDACTED-AWS-ACCESS-KEY>",
        )

    def test_redacts_aws_identity_prefix(self) -> None:
        self._assert_single_redaction(
            "identity AIDA1234567890ABCDEF",
            "aws_access_key",
            "<REDACTED-AWS-ACCESS-KEY>",
        )

    def test_redacts_aws_principal_prefix(self) -> None:
        self._assert_single_redaction(
            "principal ANPA1234567890ABCDEF",
            "aws_access_key",
            "<REDACTED-AWS-ACCESS-KEY>",
        )

    def test_redacts_aws_instance_profile_prefix(self) -> None:
        self._assert_single_redaction(
            "ec2 AIPA1234567890ABCDEF instance",
            "aws_access_key",
            "<REDACTED-AWS-ACCESS-KEY>",
        )

    def test_redacts_aws_public_key_prefix(self) -> None:
        self._assert_single_redaction(
            "pubkey APKA1234567890ABCDEF active",
            "aws_access_key",
            "<REDACTED-AWS-ACCESS-KEY>",
        )

    def test_redacts_generic_secret_assignment_value_only(self) -> None:
        redacted, findings = redact_secrets("password=hunter22")

        self.assertEqual(redacted, "password=<REDACTED-SECRET>")
        self.assertEqual([(f.kind, f.count) for f in findings], [("generic_secret_assign", 1)])

    def test_redacts_db_connection_string(self) -> None:
        self._assert_single_redaction(
            "db postgresql://alice:correcthorsebatterystaple@db.example.com/app",
            "db_connection_string",
            "<REDACTED-DB-URI>",
        )

    def test_no_secret_returns_text_unchanged(self) -> None:
        text = "feat: update docs\n\nNo credentials here."

        redacted, findings = redact_secrets(text)

        self.assertEqual(redacted, text)
        self.assertEqual(findings, [])

    def test_multiple_occurrences_accumulate_count(self) -> None:
        redacted, findings = redact_secrets(
            "sk-abcdefghijklmnopqrstuvwxyz123456 and sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ789012"
        )

        self.assertEqual(redacted.count("<REDACTED-OPENAI-KEY>"), 2)
        self.assertEqual([(f.kind, f.count) for f in findings], [("openai_key", 2)])

    def test_secret_at_start_of_string(self) -> None:
        redacted, findings = redact_secrets("AKIA1234567890ABCDEF at start")

        self.assertTrue(redacted.startswith("<REDACTED-AWS-ACCESS-KEY>"))
        self.assertEqual([(f.kind, f.count) for f in findings], [("aws_access_key", 1)])

    def test_secret_at_end_of_string(self) -> None:
        redacted, findings = redact_secrets("ends with eyJaaaaaaaa.bbbbbbbbb.ccccccccc")

        self.assertTrue(redacted.endswith("<REDACTED-JWT>"))
        self.assertEqual([(f.kind, f.count) for f in findings], [("jwt", 1)])

    def test_secret_surrounded_by_newlines(self) -> None:
        redacted, findings = redact_secrets("\nsk-ant-abcdefghijklmnopqrstuvwxyz\n")

        self.assertEqual(redacted, "\n<REDACTED-ANTHROPIC-KEY>\n")
        self.assertEqual([(f.kind, f.count) for f in findings], [("anthropic_key", 1)])


_SECRET_DIFF = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,1 +1,2 @@\n"
    " existing\n"
    "+OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456\n"
)


def _fake_generate_commit_message(
    diff, subjects, samples, model, context=None, use_cache=True,
):
    """Mock LLM that mirrors the real path: sanitizes the diff into the ContextVar."""
    prompt_safety.sanitize_text(diff)
    return "fix: redact"


def _fake_analyze_splits(diff, files, subjects, samples, model):
    prompt_safety.sanitize_text(diff)
    return [
        splitter.CommitGroup(message="fix: redact", files=files, rationale=""),
    ]


def _fake_analyze_hunk_splits(file_patches, subjects, samples, model):
    for fp in file_patches:
        prompt_safety.sanitize_text(fp.render())
    return [
        hunks.HunkGroup(
            message="fix: redact",
            refs=[hunks.HunkRef(path=fp.path, index=0) for fp in file_patches if fp.hunks],
            rationale="",
        ),
    ]


def _fake_pr_generate(base_ref, commits, diff, pr_samples, model, use_cache=True):
    from commitr import pr as _pr
    prompt_safety.sanitize_text(diff)
    return _pr.PullRequest(title="fix: redact", body="redaction body")


class RedactionFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        prompt_safety.collect_and_clear_findings()

    def tearDown(self) -> None:
        prompt_safety.collect_and_clear_findings()

    def _capture_stderr(self) -> tuple[io.StringIO, Console]:
        sink = io.StringIO()
        return sink, Console(file=sink, force_terminal=False, color_system=None)

    def test_prompt_safety_collects_and_clears_redaction_findings(self) -> None:
        prompt_safety.sanitize_text("sk-proj-abcdefghijklmnopqrstuvwxyz123456")

        self.assertEqual(
            prompt_safety.collect_and_clear_findings(),
            [("openai_key", 1)],
        )
        self.assertEqual(prompt_safety.collect_and_clear_findings(), [])

    def test_run_commit_prints_redaction_feedback_to_stderr(self) -> None:
        sink, stderr_console = self._capture_stderr()
        with mock.patch.multiple(
            commitr,
            stderr_console=stderr_console,
            _resolve_issue_context=mock.MagicMock(return_value=None),
        ), mock.patch.multiple(
            commitr.git,
            in_repo=mock.MagicMock(return_value=True),
            has_staged_changes=mock.MagicMock(return_value=True),
            staged_diff_for_llm=mock.MagicMock(return_value=_SECRET_DIFF),
            staged_files=mock.MagicMock(return_value=["app.py"]),
            recent_commits=mock.MagicMock(return_value=[]),
            recent_commit_samples=mock.MagicMock(return_value=[]),
        ), mock.patch.object(
            commitr.config, "resolve_model", return_value="test/model",
        ), mock.patch.object(
            commitr.doctor, "analyze_staged_changes", return_value=[],
        ), mock.patch.object(
            commitr.llm,
            "generate_commit_message",
            side_effect=_fake_generate_commit_message,
        ):
            commitr._run_commit(
                model=None, provider=None, yes=False, dry_run=True, no_cache=True,
            )

        self.assertIn(
            "Redacted 1 secret(s) before sending: 1 openai_key.",
            sink.getvalue(),
        )

    def test_split_flow_prints_redaction_feedback_to_stderr(self) -> None:
        sink, stderr_console = self._capture_stderr()
        multi_diff = _SECRET_DIFF + (
            "diff --git a/b.py b/b.py\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -1,1 +1,2 @@\n"
            " existing\n"
            "+pass\n"
        )
        with mock.patch.multiple(
            commitr,
            stderr_console=stderr_console,
            _resolve_issue_context=mock.MagicMock(return_value=None),
        ), mock.patch.multiple(
            commitr.git,
            in_repo=mock.MagicMock(return_value=True),
            has_staged_changes=mock.MagicMock(return_value=True),
            staged_diff_for_llm=mock.MagicMock(return_value=multi_diff),
            staged_diff_for_patch=mock.MagicMock(return_value=multi_diff),
            staged_files=mock.MagicMock(return_value=["app.py", "b.py"]),
            recent_commits=mock.MagicMock(return_value=[]),
            recent_commit_samples=mock.MagicMock(return_value=[]),
        ), mock.patch.object(
            commitr.config, "resolve_model", return_value="test/model",
        ), mock.patch.object(
            commitr.doctor, "analyze_staged_changes", return_value=[],
        ), mock.patch.object(
            commitr.splitter, "analyze_splits", side_effect=_fake_analyze_splits,
        ):
            commitr._run_commit(
                model=None, provider=None, yes=True, dry_run=True,
                split=True, no_cache=True,
            )

        self.assertIn("Redacted", sink.getvalue())
        self.assertIn("openai_key", sink.getvalue())

    def test_hunks_split_flow_prints_redaction_feedback_to_stderr(self) -> None:
        sink, stderr_console = self._capture_stderr()
        two_hunk_diff = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,1 +1,2 @@\n"
            " existing\n"
            "+OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456\n"
            "@@ -10,1 +11,2 @@\n"
            " other\n"
            "+pass\n"
        )
        with mock.patch.multiple(
            commitr,
            stderr_console=stderr_console,
            _resolve_issue_context=mock.MagicMock(return_value=None),
        ), mock.patch.multiple(
            commitr.git,
            in_repo=mock.MagicMock(return_value=True),
            has_staged_changes=mock.MagicMock(return_value=True),
            staged_diff_for_llm=mock.MagicMock(return_value=two_hunk_diff),
            staged_diff_for_patch=mock.MagicMock(return_value=two_hunk_diff),
            staged_files=mock.MagicMock(return_value=["app.py"]),
            recent_commits=mock.MagicMock(return_value=[]),
            recent_commit_samples=mock.MagicMock(return_value=[]),
        ), mock.patch.object(
            commitr.config, "resolve_model", return_value="test/model",
        ), mock.patch.object(
            commitr.doctor, "analyze_staged_changes", return_value=[],
        ), mock.patch.object(
            commitr.hunks, "analyze_hunk_splits", side_effect=_fake_analyze_hunk_splits,
        ):
            commitr._run_commit(
                model=None, provider=None, yes=True, dry_run=True,
                split=True, hunks_split=True, no_cache=True,
            )

        self.assertIn("Redacted", sink.getvalue())
        self.assertIn("openai_key", sink.getvalue())

    def test_pr_command_prints_redaction_feedback_to_stderr(self) -> None:
        sink, stderr_console = self._capture_stderr()
        with mock.patch.object(
            commitr, "stderr_console", stderr_console,
        ), mock.patch.object(
            commitr.git, "in_repo", return_value=True,
        ), mock.patch.multiple(
            commitr.pr,
            detect_base_branch=mock.MagicMock(return_value="origin/main"),
            commits_since=mock.MagicMock(return_value=["feat: x"]),
            diff_against=mock.MagicMock(return_value=_SECRET_DIFF),
            recent_pr_titles=mock.MagicMock(return_value=[]),
            generate=mock.MagicMock(side_effect=_fake_pr_generate),
        ), mock.patch.object(
            commitr.config, "resolve_model", return_value="test/model",
        ):
            commitr.pr_cmd(
                model=None, provider=None, base=None,
                create=False, yes=True, dry_run=True, no_cache=True,
            )

        self.assertIn("Redacted", sink.getvalue())
        self.assertIn("openai_key", sink.getvalue())

    def test_redaction_reporter_prints_on_llm_failure(self) -> None:
        """Findings accumulated before an LLM exception must still reach stderr."""
        sink, stderr_console = self._capture_stderr()

        def failing_llm(diff, subjects, samples, model, context=None, use_cache=True):
            prompt_safety.sanitize_text(diff)
            raise RuntimeError("LLM exploded")

        import typer
        with mock.patch.multiple(
            commitr,
            stderr_console=stderr_console,
            _resolve_issue_context=mock.MagicMock(return_value=None),
        ), mock.patch.multiple(
            commitr.git,
            in_repo=mock.MagicMock(return_value=True),
            has_staged_changes=mock.MagicMock(return_value=True),
            staged_diff_for_llm=mock.MagicMock(return_value=_SECRET_DIFF),
            staged_files=mock.MagicMock(return_value=["app.py"]),
            recent_commits=mock.MagicMock(return_value=[]),
            recent_commit_samples=mock.MagicMock(return_value=[]),
        ), mock.patch.object(
            commitr.config, "resolve_model", return_value="test/model",
        ), mock.patch.object(
            commitr.doctor, "analyze_staged_changes", return_value=[],
        ), mock.patch.object(
            commitr.llm, "generate_commit_message", side_effect=failing_llm,
        ):
            with self.assertRaises(typer.Exit):
                commitr._run_commit(
                    model=None, provider=None, yes=False, dry_run=True, no_cache=True,
                )

        self.assertIn(
            "Redacted 1 secret(s) before sending: 1 openai_key.",
            sink.getvalue(),
        )

    def test_hook_fill_cmd_prints_redaction_feedback_to_stderr(self) -> None:
        """The prepare-commit-msg hook path must also surface redaction findings."""
        sink, stderr_console = self._capture_stderr()
        captured: dict[str, str] = {}

        def fake_fill(msg_file, message):
            captured["msg"] = message

        with mock.patch.object(
            commitr, "stderr_console", stderr_console,
        ), mock.patch.multiple(
            commitr.git,
            in_repo=mock.MagicMock(return_value=True),
            has_staged_changes=mock.MagicMock(return_value=True),
            staged_diff_for_llm=mock.MagicMock(return_value=_SECRET_DIFF),
            recent_commits=mock.MagicMock(return_value=[]),
            recent_commit_samples=mock.MagicMock(return_value=[]),
        ), mock.patch.object(
            commitr.config, "resolve_model", return_value="test/model",
        ), mock.patch.object(
            commitr.issue, "detect_issue_from_branch", return_value=None,
        ), mock.patch.object(
            commitr.llm, "generate_commit_message",
            side_effect=_fake_generate_commit_message,
        ), mock.patch.object(
            commitr.hook, "fill_message_file", side_effect=fake_fill,
        ):
            commitr.hook_fill_cmd(msg_file="/tmp/COMMIT_EDITMSG")

        self.assertIn(
            "Redacted 1 secret(s) before sending: 1 openai_key.",
            sink.getvalue(),
        )
        self.assertIn("fix: redact", captured["msg"])

    def test_redaction_reporter_swallows_print_failure_silently(self) -> None:
        """A failing stderr print must NOT mask the original LLM exception."""
        with mock.patch.object(
            commitr, "_print_redaction_findings",
            side_effect=RuntimeError("stderr is broken"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                with commitr._report_redactions():
                    raise RuntimeError("LLM exploded")

        # The original LLM exception propagates, not the print failure.
        self.assertEqual(str(ctx.exception), "LLM exploded")

    def test_redaction_reporter_clears_stale_findings_on_entry(self) -> None:
        """Pre-existing findings in the buffer should NOT bleed into the next report."""
        sink, stderr_console = self._capture_stderr()
        # Pollute the buffer before entering the context manager.
        prompt_safety.sanitize_text("leftover sk-proj-abcdefghijklmnopqrstuvwxyz789012")

        with mock.patch.object(commitr, "stderr_console", stderr_console):
            with commitr._report_redactions():
                pass  # no LLM call, no new findings

        # Stale finding should have been cleared on entry, so report is empty.
        self.assertEqual(sink.getvalue(), "")


class DeprecatedGitAliasTests(unittest.TestCase):
    def test_staged_diff_alias_emits_deprecation_warning(self) -> None:
        original_staged_diff_for_llm = git.staged_diff_for_llm
        git.staged_diff_for_llm = lambda: "diff output"
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.assertEqual(git.staged_diff(), "diff output")
        finally:
            git.staged_diff_for_llm = original_staged_diff_for_llm

        self.assertTrue(
            any(item.category is DeprecationWarning for item in caught),
            "staged_diff() should emit DeprecationWarning",
        )


if __name__ == "__main__":
    unittest.main()
