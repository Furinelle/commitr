# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-05-26

### Added
- **Diff cache** at `~/.cache/commitr/` — repeated runs on the same staged diff
  return instantly without an LLM round-trip. LRU-by-mtime, 7-day TTL, 200-entry cap.
  Invalidated by changes to model, diff, or style (recent commit subjects).
- `commitr cache` — inspect entries / disk usage; `commitr cache --clear` to wipe.
- `--no-cache` flag (and automatic bypass on regenerate) for forced fresh calls.
- **Issue context injection** — `--issue N` fetches issue title/body/labels via `gh`
  and feeds it into the prompt so the model knows *why* the change is being made.
  Auto-detects an issue number from branch names like `feat/123-foo`,
  `fix-issue-42-crash`, `gh-777`. Pass `--no-issue` to opt out.
- **`commitr pr` subcommand** — generate a PR title + body from this branch's
  diff vs base. Auto-detects `origin/main`/`origin/master`. Optional `--create`
  invokes `gh pr create`. Style-learns from recent merged PR titles.
- **Hunk-level commit splitting** — `commitr --split --hunks` splits *within* a
  file, not just file-by-file. Parses the unified diff, asks the LLM to group
  hunks, and stages each group via `git apply --cached`. Renames / binary diffs
  / mode changes stay atomic. The roadmap's #1 differentiator vs aicommits /
  opencommit / aicommit2.

### Changed
- `llm.generate_commit_message` now accepts `context=` (optional issue/PR context)
  and `use_cache=` parameters. Backwards-compatible (both keyword-only with defaults).
- Default model fallback removed: `generate_commit_message` now raises if no
  model is configured instead of silently using a stale `gpt-4o-mini` default.

### Tests
- 27 new tests (cache, issue branch detection / formatting, hunks parse / group /
  render). Total: 46 tests, all green.

## [0.2.1] — 2026-05-26

### Changed
- CI/CD pipeline: GitHub Actions test workflow + OIDC trusted publishing to PyPI on tag push.
- README install section updated to show `pip install commitr` as primary install method.

## [0.2.0] — 2026-05-26

### Added
- Multi-provider support with **7 presets**: `deepseek`, `openai`, `anthropic`, `gemini`, `mistral`, `groq`, `ollama`.
- Auto-detection: with any provider's API key set, `commitr` picks it without further config.
- Config file at `~/.config/commitr/config.toml` + `.env` loading at `~/.config/commitr/.env`.
- `--split` / `-s` smart commit splitting (file-level LLM grouping); `--yes` for non-interactive multi-commit.
- `prepare-commit-msg` git-hook mode: `commitr install-hook` / `uninstall-hook`.
- `commitr style` — print the repo's commit-message style profile (deterministic, no LLM call).
- `commitr doctor` — preflight checks for staged diff (binary, large, lockfile-only, no model, no changes).
- Automatic doctor preflight in the main commit flow — errors short-circuit before any API call.
- Optional `Co-Authored-By` trailer via `COMMITR_COAUTHOR` env or `[default].coauthor` in config.
- `--version` / `-V` flag.
- MIT LICENSE file.
- pytest test suite (19 tests covering config, style, doctor, hook, splitter, CLI).
- PyPI metadata: classifiers, keywords, project URLs, license, authors.

### Changed
- Default provider models refreshed to **May 2026** versions: DeepSeek V4 Flash, GPT-5.4 mini, Claude Haiku 4.5, Gemini 3.5 Flash, Mistral Small 4, Qwen3 32B on Groq.
- `_edit_in_editor` switched from `os.system` to `subprocess.run` for shell-injection safety and editor-failure surfacing.
- `config.toml` template no longer hard-codes a provider — auto-detect is the default; the line is commented for opt-in pinning.
- LiteLLM `max_tokens` raised from 300 to 1000 to prevent truncated commit bodies.
- Suppressed noisy LiteLLM import-time warnings about optional AWS providers.

### Fixed
- Commit body truncation on longer messages (`max_tokens=300` was too tight).
- Editor non-zero exit is now surfaced instead of silently producing an empty message.

## [0.1.0] — 2026-05-24

### Added
- Initial MVP: read staged diff → generate commit message via LLM → interactive accept / edit / regenerate → commit.
- Style learning from `git log` (last 20 subjects + last 5 full commit bodies as few-shot examples).
- Configurable via `COMMITR_MODEL` env var (any LiteLLM model string).
