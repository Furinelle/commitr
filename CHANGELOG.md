# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
