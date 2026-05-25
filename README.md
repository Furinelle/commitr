# commitr

AI-generated git commit messages that **learn your project's style** — language, format, scope, emoji, body conventions. Works with OpenAI, Anthropic, local Ollama, and anything else [LiteLLM](https://github.com/BerriAI/litellm) supports.

> Stage your changes, run `commitr`, accept / edit / regenerate, commit. That's it.

## Install

Requires Python ≥ 3.12 and [uv](https://github.com/astral-sh/uv).

```bash
git clone <this-repo> ~/Documents/Github/commitr
cd ~/Documents/Github/commitr
uv sync

# (optional) put it on your PATH
ln -s "$PWD/.venv/bin/commitr" /usr/local/bin/commitr
```

## Quick start

```bash
# pick a provider via env var
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
# or run a local model — no key, no cost, no data leaves your machine
export COMMITR_MODEL=ollama/qwen2.5-coder:7b

cd /your/project
git add somefile
commitr
```

You'll get an interactive prompt:

```
╭─────────── Proposed commit ───────────╮
│ feat(parser): handle empty heredoc    │
│                                       │
│ Returned an empty string instead of   │
│ raising; fixes #42.                   │
╰───────────────────────────────────────╯
? What now?
❯ Accept and commit
  Edit before committing
  Regenerate
  Cancel
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COMMITR_MODEL` | `gpt-4o-mini` | Any [LiteLLM model string](https://docs.litellm.ai/docs/providers) |
| `OPENAI_API_KEY` | — | OpenAI |
| `ANTHROPIC_API_KEY` | — | Anthropic |
| `EDITOR` | `vim` | Editor opened by "Edit before committing" |

### Model recipes

```bash
# cheap and good (default)
export COMMITR_MODEL=gpt-4o-mini

# Anthropic — great at matching style
export COMMITR_MODEL=claude-haiku-4-5
export ANTHROPIC_API_KEY=sk-ant-...

# local, zero-cost, zero-leakage
brew install ollama && ollama serve &
ollama pull qwen2.5-coder:7b
export COMMITR_MODEL=ollama/qwen2.5-coder:7b

# DeepSeek
export COMMITR_MODEL=deepseek/deepseek-chat
export DEEPSEEK_API_KEY=...
```

## Flags

```
commitr                 # interactive (default)
commitr --yes           # commit without asking (use in scripts)
commitr --dry-run       # print the message; don't commit
commitr --model claude-haiku-4-5
```

## How style learning works

For every run, `commitr` collects:

- The last 20 commit **subjects** (broad style scan)
- The last 5 full commit messages (subject + body — few-shot examples)

These go into the prompt with explicit instructions to detect and match: **language, scope usage, emoji usage, body usage, and type vocabulary**. So if your repo writes Chinese commits with `(scope)` and gitmoji, you'll get Chinese commits with `(scope)` and gitmoji.

## Roadmap

- [x] MVP: read staged diff → LLM → interactive accept/edit/regen → commit
- [x] Style learning from `git log`
- [ ] Smart commit splitting (suggest breaking large diffs into multiple commits)
- [ ] `prepare-commit-msg` git-hook mode
- [ ] Diff caching (don't re-call the LLM for identical diffs)
- [ ] Binary diff detection & skip
- [ ] Homebrew tap & PyPI release

## Project layout

```
src/commitr/
├── __init__.py   # Typer CLI + main flow
├── git.py        # subprocess wrappers around git
└── llm.py        # LiteLLM call + style-aware prompt
```

## License

MIT.
