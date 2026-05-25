# commitr

AI-generated git commit messages that **learn your project's style** — language, format, scope, emoji, body conventions. Built-in support for **7 AI providers** and 100+ models via [LiteLLM](https://github.com/BerriAI/litellm).

> Stage your changes, run `commitr`, accept / edit / regenerate, commit. That's it.

## Supported providers

Out-of-the-box presets — see them anytime with `commitr providers`:

| Preset | Default model | Key env | Notes |
|---|---|---|---|
| `deepseek` | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY` | cheap, fast, strong on Chinese |
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY` | reliable default |
| `anthropic` | `claude-haiku-4-5` | `ANTHROPIC_API_KEY` | excellent style matching |
| `gemini` | `gemini/gemini-2.0-flash-exp` | `GEMINI_API_KEY` | free tier available |
| `mistral` | `mistral/mistral-small-latest` | `MISTRAL_API_KEY` | EU-hosted |
| `groq` | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` | blazing fast inference |
| `ollama` | `ollama/qwen2.5-coder:7b` | — | local, zero-cost, zero-leakage |

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
commitr --provider deepseek            # use a preset, just for this run
commitr --model deepseek/deepseek-reasoner   # exact model override
commitr providers                      # subcommand: list providers
commitr config --init                  # subcommand: write template config
```

## How style learning works

For every run, `commitr` collects:

- The last **20 commit subjects** (broad style scan)
- The last **5 full commit messages** (subject + body — few-shot examples)

These go into the prompt with explicit instructions to detect and match: **language, scope usage, emoji usage, body usage, and type vocabulary**. So if your repo writes Chinese commits with `(scope)` and gitmoji, you'll get Chinese commits with `(scope)` and gitmoji.

## Roadmap

- [x] MVP: read staged diff → LLM → interactive accept/edit/regen → commit
- [x] Style learning from `git log`
- [x] Multi-provider presets + config file + `.env` loading
- [ ] Smart commit splitting (suggest breaking large diffs into multiple commits)
- [ ] `prepare-commit-msg` git-hook mode
- [ ] Diff caching (don't re-call the LLM for identical diffs)
- [ ] Binary diff detection & skip
- [ ] Homebrew tap & PyPI release

## Project layout

```
src/commitr/
├── __init__.py   # Typer CLI: callback + `providers` / `config` subcommands
├── config.py     # provider presets, config & .env loading, model resolution
├── git.py        # subprocess wrappers around git
└── llm.py        # LiteLLM call + style-aware prompt
```

## License

MIT.
