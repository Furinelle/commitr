from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from commitr import config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_paths = (config.CONFIG_DIR, config.CONFIG_FILE, config.ENV_FILE)
        self._old_env = os.environ.copy()
        self.tmp = tempfile.TemporaryDirectory()
        cfg_dir = Path(self.tmp.name) / "commitr"
        config.CONFIG_DIR = cfg_dir
        config.CONFIG_FILE = cfg_dir / "config.toml"
        config.ENV_FILE = cfg_dir / ".env"

    def tearDown(self) -> None:
        config.CONFIG_DIR, config.CONFIG_FILE, config.ENV_FILE = self._old_paths
        os.environ.clear()
        os.environ.update(self._old_env)
        self.tmp.cleanup()

    def test_env_file_does_not_override_existing_environment(self) -> None:
        config.CONFIG_DIR.mkdir(parents=True)
        config.ENV_FILE.write_text(
            "DEEPSEEK_API_KEY=from-file\nOPENAI_API_KEY='quoted-file'\n"
        )
        os.environ["DEEPSEEK_API_KEY"] = "from-env"

        config.load_env_file()

        self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "from-env")
        self.assertEqual(os.environ["OPENAI_API_KEY"], "quoted-file")

    def test_init_template_preserves_zero_config_auto_detection(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test"

        config.write_config_template()

        template = config.CONFIG_FILE.read_text()
        self.assertNotIn('provider = "deepseek"', template.splitlines())
        self.assertIn('# provider = "deepseek"', template)
        self.assertEqual(
            config.resolve_model(cli_model=None, cli_provider=None),
            config.PROVIDERS["openai"].model,
        )

    def test_configured_provider_still_overrides_auto_detection(self) -> None:
        config.CONFIG_DIR.mkdir(parents=True)
        config.CONFIG_FILE.write_text('[default]\nprovider = "deepseek"\n')
        os.environ["OPENAI_API_KEY"] = "sk-test"

        self.assertEqual(
            config.resolve_model(cli_model=None, cli_provider=None),
            config.PROVIDERS["deepseek"].model,
        )


if __name__ == "__main__":
    unittest.main()
