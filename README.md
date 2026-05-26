# commitr

[English](README.md) · [简体中文](README.zh-CN.md)

AI-generated git commit messages that **learn your project's style** — language, format, scope, emoji, body conventions. Built-in support for **7 AI providers** and 100+ models via [LiteLLM](https://github.com/BerriAI/litellm).

> Stage your changes, run `commitr`, accept / edit / regenerate, commit. That's it.

**Why commitr stands out** — features no other AI commit tool has:

- **Hunk-level splitting** (`--split --hunks`) — split *within* a single file, not just by file
- **Diff cache** — instant on repeat diffs, zero API cost on regenerate
- **Issue context** (`--issue N`) — model sees the issue title/body so it knows *why*, not just *what*
- **PR mode** (`commitr pr`) — same style-learning pipeline applied to pull-request descriptions

## Supported providers

Out-of-the-box presets — see them anytime with `commitr providers`:

| Preset | Default model | Key env | Notes |
|---|---|---|---|
| `deepseek` | `deepseek/deepseek-v4-flash` | `DEEPSEEK_API_KEY` | V4 Flash · 1M ctx · ~$0.14/$0.28 per Mtok · strong on Chinese |
| `openai` | `gpt-5.4-mini` | `OPENAI_API_KEY` | GPT-5.4 mini · reliable, good quality/cost balance |
| `anthropic` | `claude-haiku-4-5` | `ANTHROPIC_API_KEY` | Haiku 4.5 · excellent style matching, cheap |
| `gemini` | `gemini/gemini-3.5-flash` | `GEMINI_API_KEY` | Gemini 3.5 Flash · free tier available |
| `mistral` | `mistral/mistral-small-latest` | `MISTRAL_API_KEY` | Mistral Small 4 · EU-hosted · $0.15/$0.60 per Mtok |
| `groq` | `groq/qwen/qwen3-32b` | `GROQ_API_KEY` | Qwen3 32B · blazing fast inference |
| `ollama` | `ollama/qwen2.5-coder:7b` | — | local, zero-cost, zero-leakage |

> Defaults verified **May 2026**. Use `--model <litellm-string>` for any other model (DeepSeek V4 Pro, Claude Sonnet 4.6, GPT-5.5, Gemini 3.5 Pro, …).

Want a different model from the same provider? Use `--model <litellm-string>` directly.

## Install

Requires Python ≥ 3.12.

```bash
pip install commitr
```

Or with [uv](https://github.com/astral-sh/uv) (recommended — pulls a clean isolated environment):

```bash
uv tool install commitr
```

<details>
<summary>Install from source (for development)</summary>

```bash
git clone https://github.com/Furinelle/commitr
cd commitr
uv sync
ln -s "$PWD/.venv/bin/commitr" /usr/local/bin/commitr  # optional: add to PATH
```

</details>

## Quick start

Zero-config path — just export a key, commitr auto-detects:

```bash
export DEEPSEEK_API_KEY=sk-...        # (or OPENAI_API_KEY, ANTHROPIC_API_KEY, ...)

cd /your/project
git add somefile
commitr                                # uses the first provider whose key is set
```

You'll get an interactive prompt:

```
╭── Proposed commit (via deepseek/deepseek-v4-flash) ────╮
│ feat(parser): handle empty heredoc                     │
│                                                        │
│ Returned an empty string instead of raising; fixes #42.│
╰────────────────────────────────────────────────────────╯
? What now?
❯ Accept and commit
  Edit before committing
  Regenerate
  Cancel
```

## Configuration

`commitr` reads config from three layers, with this **precedence**:

1. CLI flags: `--model` > `--provider`
2. Environment: `$COMMITR_MODEL`, plus the provider's key env vars
3. Config file: `~/.config/commitr/config.toml`
4. Auto-detect: first provider with a key set in the environment

### Set it once and forget it

```bash
commitr config --init
```

That creates two files:

- `~/.config/commitr/config.toml` — pick your default provider/model
- `~/.config/commitr/.env` — put your API keys here (loaded automatically)

Example `config.toml`:

```toml
[default]
# Leave this commented to auto-detect from configured API keys,
# or uncomment to pin a default provider.
# provider = "deepseek"
# model = "deepseek/deepseek-reasoner"   # or override with an exact model string
```

Example `.env`:

```
DEEPSEEK_API_KEY=sk-...
OPENAI_API_KEY=sk-...
```

### Inspect

```bash
commitr providers     # table of presets + which keys are configured
commitr config        # show the resolved model + config file locations
```

## CLI

```bash
commitr                                # interactive (default)
commitr --yes                          # commit without asking (CI-friendly)
commitr --dry-run                      # print the message; don't commit
commitr --split                        # file-level multi-commit split
commitr --split --hunks                # HUNK-level split (within files) — v0.3+
commitr --split --yes                  # non-interactive split (commits every group)
commitr --issue 42                     # inject issue #42 as context (via `gh`)
commitr --no-issue                     # skip auto-detect-from-branch issue context
commitr --no-cache                     # force a fresh LLM call
commitr --version                      # print version and exit
commitr --provider deepseek            # use a preset, just for this run
commitr --model deepseek/deepseek-reasoner   # exact model override
commitr providers                      # subcommand: list providers
commitr config --init                  # subcommand: write template config
commitr style                          # inspect learned commit style
commitr doctor                         # check staged changes before generation
commitr cache                          # inspect message cache; --clear to wipe
commitr pr                             # generate a PR title + body
commitr pr --create                    # ...and open it via `gh pr create`
commitr install-hook                   # install prepare-commit-msg git hook
commitr uninstall-hook                 # remove the git hook
```

## Git-hook mode (`commitr install-hook`)

Want plain `git commit` to "just work" with AI? Install the hook once per repo:

```bash
cd /your/project
commitr install-hook
```

From then on, `git commit` (no `-m`) opens your editor with a pre-filled message:

```bash
git add some-file
git commit              # editor opens with AI-generated message already there
# edit / save / done
```

- Skips when you pass `-m`, on merge / squash commits, or if `commitr` isn't on `PATH`
- Silently falls back to an empty editor if the LLM call fails (your commit isn't blocked)
- Remove it any time: `commitr uninstall-hook`

## Smart commit splitting (`--split`)

When you staged a feature **and** an unrelated bugfix **and** some docs in one
go, `commitr --split` asks the model to group your staged files into independent
commits. You then walk through each group:

```
╭─ Group 1/3 · 2 file(s) · Adds the new heredoc edge case to the parser. ─╮
│ feat(parser): handle empty heredoc                                       │
│                                                                          │
│ Files:                                                                   │
│   src/parser.py                                                          │
│   src/utils.py                                                           │
╰──────────────────────────────────────────────────────────────────────────╯
? What now?
❯ Commit this group
  Edit message, then commit
  Skip this group
  Stop (abort remaining)
```

- Default is file-level; pass `--hunks` to split *within* a single file too (see below).
- The model is instructed to only split clearly independent changes.
- Stopping or skipping leaves untouched files re-staged so you can finish manually.

## How style learning works

For every run, `commitr` collects:

- The last **20 commit subjects** (broad style scan)
- The last **5 full commit messages** (subject + body — few-shot examples)

These go into the prompt with explicit instructions to detect and match: **language, scope usage, emoji usage, body usage, and type vocabulary**. So if your repo writes Chinese commits with `(scope)` and gitmoji, you'll get Chinese commits with `(scope)` and gitmoji.

You can inspect the inferred profile without calling an LLM:

```bash
commitr style
```

Example output:

```
╭──────────── Commit style profile ────────────╮
│ Language: English                            │
│ Conventional commits: yes                    │
│ Emoji prefix: no                             │
│ Body usage: occasional                       │
│ Types: feat, fix, docs                       │
│ Scopes: cli, config                          │
╰──────────────────────────────────────────────╯
```

## Commit doctor

Before asking the model, you can run a local preflight check:

```bash
commitr doctor
```

`doctor` catches deterministic issues such as:

- no staged changes
- missing model/provider configuration
- binary diffs where content is invisible to the model
- very large diffs that may lose details
- lockfile-only commits that may be missing the dependency change

## Issue context (`--issue`)

`commitr` knows that *why* matters more than *what*. Point it at an issue and
the model sees the issue's title, body, labels, and state when drafting:

```bash
commitr --issue 42                     # explicit
commitr                                 # auto-detected from branch `feat/42-foo`
commitr --no-issue                      # skip auto-detect
```

Auto-detect matches common patterns: `feat/123-name`, `fix-issue-42-crash`,
`gh-777`, `issue/9000`. Uses `gh` under the hood, so you need it installed and
authenticated — but it fails silently if not available (your commit isn't blocked).

## Diff cache

Identical diffs produce identical messages. Cache hits return instantly with
no API call — useful for regen, doctor, and frequent staging churn:

```bash
commitr cache                          # show entries + disk usage
commitr cache --clear                  # wipe everything
commitr --no-cache                     # one-off bypass
```

Cache lives at `~/.cache/commitr/` (or `$XDG_CACHE_HOME/commitr/`). LRU-by-mtime,
7-day TTL, 200-entry cap. Invalidated by changes in model, diff, or repo style.

## PR description mode (`commitr pr`)

Same style-learning pipeline, but for pull requests — learns from your repo's
recent merged PR titles and your branch's commits + diff:

```bash
commitr pr                             # print proposal
commitr pr --create                    # generate + `gh pr create` in one go
commitr pr --base origin/develop       # different base
```

## Hunk-level splitting (`--split --hunks`)

The roadmap headliner. `commitr --split` already groups *files* into independent
commits. With `--hunks` it goes one level deeper — splitting *within* a file:

```bash
git add big-refactor.py                 # staged 3 unrelated hunks in one file
commitr --split --hunks
# → group 1: hunks #0 + #2 (the feature)
# → group 2: hunk #1 (the unrelated bugfix)
# Each group is staged via `git apply --cached` and committed separately.
```

Renames, binary diffs, and mode changes stay atomic. If the model can't parse
or returns garbage, the remaining hunks are re-staged so you can finish manually.

## Roadmap

- [x] MVP: read staged diff → LLM → interactive accept/edit/regen → commit
- [x] Style learning from `git log`
- [x] Multi-provider presets + config file + `.env` loading
- [x] Smart commit splitting (file-level, `--split`)
- [x] `prepare-commit-msg` git-hook mode (`commitr install-hook`)
- [x] Optional `Co-Authored-By` trailer (per-repo opt-in)
- [x] Local `style` and `doctor` inspection commands
- [x] Hunk-level commit splitting (within a file) — v0.3
- [x] Diff caching (don't re-call the LLM for identical diffs) — v0.3
- [x] Issue context injection (`--issue N` + branch auto-detect) — v0.3
- [x] PR description mode (`commitr pr`) — v0.3
- [ ] Semantic diff noise filtering (drop import re-orders, whitespace, etc.)
- [ ] Team policy file (`.commitr.toml`)
- [ ] Monorepo per-package style profiles
- [ ] Multi-provider race mode (`--race openai,anthropic,deepseek`)
- [ ] `commitr lint` — score recent commits, suggest rewrites
- [ ] Raycast extension for one-click commits on macOS
- [ ] Homebrew tap

## Project layout

```
src/commitr/
├── __init__.py   # Typer CLI: callback + subcommands
├── cache.py      # on-disk message cache (LRU + TTL)
├── config.py     # provider presets, config & .env loading, model resolution
├── doctor.py     # local staged-diff health checks
├── git.py        # subprocess wrappers around git
├── hook.py       # prepare-commit-msg install / uninstall / fill
├── hunks.py      # hunk-level diff parsing + grouping (`--split --hunks`)
├── issue.py      # branch → issue # auto-detect + `gh` context fetch
├── llm.py        # LiteLLM call + style-aware prompt + cache
├── pr.py         # PR title + body generation (`commitr pr`)
├── splitter.py   # LLM-driven file-level multi-commit grouping (`--split`)
└── style.py      # commit history style inference
```

## License

MIT.
