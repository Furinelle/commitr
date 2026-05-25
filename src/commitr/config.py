"""Provider presets, config file loading, and model resolution."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    key_env: str | None  # None means no key required (e.g. local Ollama)
    homepage: str
    notes: str = ""


# Canonical preset per provider (verified May 2026). Power users can still
# override with --model. Models are picked for the commit-message use case:
# cheap, fast, low-temperature-friendly. Updated:
#   2026-05: DeepSeek V4 Flash, GPT-5.4 mini, Claude Haiku 4.5, Gemini 3.5
#            Flash, Mistral Small 4 (via -latest), Qwen3 32B on Groq.
PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        "deepseek", "deepseek/deepseek-v4-flash", "DEEPSEEK_API_KEY",
        "https://platform.deepseek.com",
        "V4 Flash · 1M ctx · ~$0.14/$0.28 per Mtok · strong on Chinese",
    ),
    "openai": Provider(
        "openai", "gpt-5.4-mini", "OPENAI_API_KEY",
        "https://platform.openai.com",
        "GPT-5.4 mini · reliable, good quality/cost balance",
    ),
    "anthropic": Provider(
        "anthropic", "claude-haiku-4-5", "ANTHROPIC_API_KEY",
        "https://console.anthropic.com",
        "Haiku 4.5 · excellent style matching, cheap",
    ),
    "gemini": Provider(
        "gemini", "gemini/gemini-3.5-flash", "GEMINI_API_KEY",
        "https://aistudio.google.com",
        "Gemini 3.5 Flash · free tier available",
    ),
    "mistral": Provider(
        "mistral", "mistral/mistral-small-latest", "MISTRAL_API_KEY",
        "https://console.mistral.ai",
        "Mistral Small 4 · EU-hosted · $0.15/$0.60 per Mtok",
    ),
    "groq": Provider(
        "groq", "groq/qwen/qwen3-32b", "GROQ_API_KEY",
        "https://console.groq.com",
        "Qwen3 32B · blazing fast inference",
    ),
    "ollama": Provider(
        "ollama", "ollama/qwen2.5-coder:7b", None,
        "https://ollama.com",
        "local, zero-cost, zero-leakage · bump to qwen3-coder when available",
    ),
}


CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "commitr"
CONFIG_FILE = CONFIG_DIR / "config.toml"
ENV_FILE = CONFIG_DIR / ".env"


def load_env_file() -> None:
    """Load ~/.config/commitr/.env into os.environ (without overriding existing vars)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def write_config_template() -> Path:
    """Create ~/.config/commitr/config.toml with a commented template. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        return CONFIG_FILE
    template = """# commitr configuration. Lookup precedence:
#   CLI flag (--model / --provider) > $COMMITR_MODEL > this file > auto-detect

[default]
# Pick one preset:
provider = "deepseek"

# ...or specify an exact LiteLLM model string (overrides `provider`):
# model = "deepseek/deepseek-v4-flash"

# Append a Co-Authored-By: trailer to every generated commit message.
# Useful to credit the AI partner (or yourself as orchestrator) on each commit.
# coauthor = "Claude <noreply@anthropic.com>"
"""
    CONFIG_FILE.write_text(template)
    return CONFIG_FILE


def write_env_template() -> Path:
    """Create ~/.config/commitr/.env if missing. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if ENV_FILE.exists():
        return ENV_FILE
    template = """# Put your API keys here. Uncomment and fill in the ones you use.
# DEEPSEEK_API_KEY=sk-...
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=...
# MISTRAL_API_KEY=...
# GROQ_API_KEY=...
"""
    ENV_FILE.write_text(template)
    return ENV_FILE


def resolve_model(cli_model: str | None, cli_provider: str | None) -> str:
    """Resolve the model name. Order: cli_model > cli_provider > env > config > auto-detect."""
    if cli_model:
        return cli_model
    if cli_provider:
        if cli_provider not in PROVIDERS:
            known = ", ".join(PROVIDERS)
            raise ValueError(f"Unknown provider {cli_provider!r}. Known: {known}")
        return PROVIDERS[cli_provider].model

    if env_model := os.environ.get("COMMITR_MODEL"):
        return env_model

    cfg = load_config().get("default", {})
    if model := cfg.get("model"):
        return model
    if provider := cfg.get("provider"):
        if provider not in PROVIDERS:
            raise ValueError(f"config: unknown provider {provider!r}")
        return PROVIDERS[provider].model

    # Auto-detect: first preset whose key env var is set.
    for p in PROVIDERS.values():
        if p.key_env and os.environ.get(p.key_env):
            return p.model
    if _ollama_reachable():
        return PROVIDERS["ollama"].model

    raise RuntimeError(
        "No model could be resolved. Set an API key (e.g. DEEPSEEK_API_KEY), "
        "pick a provider with --provider, or run `commitr config --init`."
    )


def coauthor_trailer() -> str | None:
    """Return the configured Co-Authored-By trailer value, or None.

    Resolution: $COMMITR_COAUTHOR env var > [default].coauthor in config.toml.
    Returns the bare 'Name <email>' string; the caller wraps it in
    'Co-Authored-By: ...'.
    """
    env = os.environ.get("COMMITR_COAUTHOR")
    if env and env.strip():
        return env.strip()
    val = load_config().get("default", {}).get("coauthor")
    if val and isinstance(val, str) and val.strip():
        return val.strip()
    return None


def provider_status() -> list[tuple[Provider, bool]]:
    """Return [(provider, has_credentials)] for every preset."""
    out: list[tuple[Provider, bool]] = []
    for p in PROVIDERS.values():
        if p.key_env is None:
            ok = _ollama_reachable()
        else:
            ok = bool(os.environ.get(p.key_env))
        out.append((p, ok))
    return out


def _ollama_reachable() -> bool:
    """Best-effort check: is a local Ollama server up?"""
    import socket

    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").replace("http://", "")
    host, _, port = host.partition(":")
    try:
        with socket.create_connection((host, int(port or 11434)), timeout=0.2):
            return True
    except OSError:
        return False
