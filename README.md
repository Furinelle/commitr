# commitr

AI-generated git commit messages that **learn your project's style** — language, format, scope, emoji, body conventions. Built-in support for **7 AI providers** and 100+ models via [LiteLLM](https://github.com/BerriAI/litellm).

> Stage your changes, run `commitr`, accept / edit / regenerate, commit. That's it.

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

Requires Python ≥ 3.12 and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/Furinelle/commitr ~/Documents/Github/commitr
cd ~/Documents/Github/commitr
uv sync

# (optional) put it on your PATH
ln -s "$PWD/.venv/bin/commitr" /usr/local/bin/commitr
```

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
╭───── Proposed commit (via deepseek/deepseek-chat) ─────╮
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
provider = "deepseek"
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
commitr --split                        # analyze diff; propose multi-commit split
commitr --split --yes                  # non-interactive split (commits every group)
commitr --version                      # print version and exit
commitr --provider deepseek            # use a preset, just for this run
commitr --model deepseek/deepseek-reasoner   # exact model override
commitr providers                      # subcommand: list providers
commitr config --init                  # subcommand: write template config
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

- File-level splitting only (no hunk-splitting — yet).
- The model is instructed to only split clearly independent changes.
- Stopping or skipping leaves untouched files re-staged so you can finish manually.

## How style learning works

For every run, `commitr` collects:

- The last **20 commit subjects** (broad style scan)
- The last **5 full commit messages** (subject + body — few-shot examples)

These go into the prompt with explicit instructions to detect and match: **language, scope usage, emoji usage, body usage, and type vocabulary**. So if your repo writes Chinese commits with `(scope)` and gitmoji, you'll get Chinese commits with `(scope)` and gitmoji.

## Roadmap

- [x] MVP: read staged diff → LLM → interactive accept/edit/regen → commit
- [x] Style learning from `git log`
- [x] Multi-provider presets + config file + `.env` loading
- [x] Smart commit splitting (file-level, `--split`)
- [x] `prepare-commit-msg` git-hook mode (`commitr install-hook`)
- [x] Optional `Co-Authored-By` trailer (per-repo opt-in)
- [ ] Hunk-level commit splitting (within a file)
- [ ] Diff caching (don't re-call the LLM for identical diffs)
- [ ] Binary diff detection & skip
- [ ] Homebrew tap & PyPI release

## Project layout

```
src/commitr/
├── __init__.py   # Typer CLI: callback + subcommands
├── config.py     # provider presets, config & .env loading, model resolution
├── git.py        # subprocess wrappers around git
├── hook.py       # prepare-commit-msg install / uninstall / fill
├── llm.py        # LiteLLM call + style-aware prompt
└── splitter.py   # LLM-driven multi-commit grouping (`--split`)
```

## License

MIT.
