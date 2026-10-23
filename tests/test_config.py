from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provider_imagegen.config import load_provider_config


class ProviderConfigTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def write_config(self, extra="", encoding="utf-8"):
        (self.root / "config.toml").write_text(
            'model_provider = "custom"\n'
            '[model_providers.custom]\n'
            'base_url = "https://images.example/v1/"\n' + extra,
            encoding=encoding,
        )

    def write_auth(self, value):
        (self.root / "auth.json").write_text(json.dumps(value), encoding="utf-8")

    def test_provider_bearer_token_works_without_auth_json(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / "config.toml").write_text(
                'model_provider = "custom"\n'
                '[model_providers.custom]\n'
                'base_url = "https://images.example/v1"\n'
                'requires_openai_auth = false\n'
                'experimental_bearer_token = "test-provider-token"\n',
                encoding="utf-8",
            )

            provider = load_provider_config(root)

            self.assertEqual(provider.api_key, "test-provider-token")
            self.assertEqual(provider.base_url, "https://images.example/v1")
            self.assertFalse((root / "auth.json").exists())

    def test_provider_env_key_works_without_auth_json(self):
        self.write_config('env_key = "CUSTOM_IMAGE_KEY"\n')
        os.environ["CUSTOM_IMAGE_KEY"] = " test-environment-key "
        provider = load_provider_config(self.root)
        self.assertEqual(provider.api_key, "test-environment-key")

    def test_provider_env_key_precedes_bearer_and_legacy_keys(self):
        self.write_config(
            'env_key = "CUSTOM_IMAGE_KEY"\n'
            'experimental_bearer_token = "test-bearer-key"\n'
        )
        self.write_auth({"OPENAI_API_KEY": "test-legacy-key"})
        os.environ.update(CUSTOM_IMAGE_KEY="test-provider-key", OPENAI_API_KEY="test-global-key")
        self.assertEqual(load_provider_config(self.root).api_key, "test-provider-key")

    def test_missing_provider_env_key_does_not_use_another_key(self):
        self.write_config(
            'env_key = "CUSTOM_IMAGE_KEY"\n'
            'experimental_bearer_token = "test-bearer-key"\n'
        )
        self.write_auth({"OPENAI_API_KEY": "test-legacy-key"})
        os.environ["OPENAI_API_KEY"] = "test-global-key"
        with self.assertRaisesRegex(ValueError, "CUSTOM_IMAGE_KEY"):
            load_provider_config(self.root)

    def test_bearer_precedes_auth_json_and_does_not_parse_it(self):
        self.write_config('experimental_bearer_token = "test-provider-key"\n')
        (self.root / "auth.json").write_text("invalid unused auth", encoding="utf-8")
        provider = load_provider_config(self.root)
        self.assertEqual(provider.api_key, "test-provider-key")
        self.assertNotIn("test-provider-key", repr(provider))

    def test_legacy_auth_json_still_works(self):
        self.write_config()
        self.write_auth({"OPENAI_API_KEY": "test-legacy-key"})
        os.environ["OPENAI_API_KEY"] = "test-global-key"
        provider = load_provider_config(self.root)
        self.assertEqual(provider.api_key, "test-legacy-key")
        self.assertEqual(provider.base_url, "https://images.example/v1")

    def test_global_openai_environment_key_fallback(self):
        self.write_config()
        os.environ["OPENAI_API_KEY"] = "test-global-key"
        self.assertEqual(load_provider_config(self.root).api_key, "test-global-key")

    def test_explicit_key_overrides_all_provider_credentials(self):
        self.write_config('env_key = "MISSING_PROVIDER_KEY"\n')
        self.assertEqual(
            load_provider_config(self.root, api_key_override=" test-override ").api_key,
            "test-override",
        )

    def test_explicit_environment_override_precedes_provider(self):
        self.write_config('experimental_bearer_token = "test-provider-key"\n')
        os.environ["ONE_OFF_KEY"] = "test-override-key"
        self.assertEqual(
            load_provider_config(self.root, api_key_env="ONE_OFF_KEY").api_key,
            "test-override-key",
        )

    def test_complete_overrides_work_without_root_files(self):
        provider = load_provider_config(
            self.root,
            base_url_override="https://temporary.example/v1/",
            api_key_override="test-override-key",
        )
        self.assertEqual(provider.base_url, "https://temporary.example/v1")
        self.assertEqual(provider.api_key, "test-override-key")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_complete_overrides_do_not_parse_unused_root_files(self):
        (self.root / "config.toml").write_text("invalid unused config", encoding="utf-8")
        (self.root / "auth.json").write_text("invalid unused auth", encoding="utf-8")
        provider = load_provider_config(
            self.root, base_url_override="https://temporary.example/v1", api_key_override="test-key"
        )
        self.assertEqual(provider.api_key, "test-key")

    def test_url_override_can_use_configured_provider_credentials(self):
        self.write_config('experimental_bearer_token = "test-provider-key"\n')
        provider = load_provider_config(self.root, base_url_override="https://temporary.example/v1")
        self.assertEqual(provider.api_key, "test-provider-key")
        self.assertEqual(provider.base_url, "https://temporary.example/v1")

    def test_url_override_and_legacy_auth_without_config(self):
        self.write_auth({"OPENAI_API_KEY": "test-legacy-key"})
        provider = load_provider_config(self.root, base_url_override="https://temporary.example/v1")
        self.assertEqual(provider.api_key, "test-legacy-key")

    def test_url_override_and_legacy_auth_without_custom_provider_table(self):
        (self.root / "config.toml").write_text('model_provider = "openai"\n', encoding="utf-8")
        self.write_auth({"OPENAI_API_KEY": "test-legacy-key"})
        provider = load_provider_config(self.root, base_url_override="https://temporary.example/v1")
        self.assertEqual(provider.api_key, "test-legacy-key")
        self.assertEqual(provider.base_url, "https://temporary.example/v1")

    def test_url_override_and_global_environment_without_root_files(self):
        os.environ["OPENAI_API_KEY"] = "test-global-key"
        provider = load_provider_config(self.root, base_url_override="https://temporary.example/v1")
        self.assertEqual(provider.api_key, "test-global-key")

    def test_explicit_missing_environment_override_fails(self):
        self.write_config('experimental_bearer_token = "test-provider-key"\n')
        with self.assertRaisesRegex(ValueError, "ONE_OFF_KEY"):
            load_provider_config(self.root, api_key_env="ONE_OFF_KEY")

    def test_empty_explicit_key_is_rejected(self):
        self.write_config('experimental_bearer_token = "test-provider-key"\n')
        with self.assertRaisesRegex(ValueError, "--api-key"):
            load_provider_config(self.root, api_key_override="")

    def test_conflicting_overrides_are_rejected_even_when_one_is_empty(self):
        with self.assertRaisesRegex(ValueError, "only one"):
            load_provider_config(self.root, api_key_override="", api_key_env="ONE_OFF_KEY")

    def test_chatgpt_oauth_tokens_are_not_used_as_api_key(self):
        self.write_config()
        self.write_auth({"OPENAI_API_KEY": None, "tokens": {"access_token": "test-oauth-token"}})
        with self.assertRaisesRegex(ValueError, "API key") as caught:
            load_provider_config(self.root)
        self.assertNotIn("test-oauth-token", str(caught.exception))

    def test_missing_credentials_explain_available_sources(self):
        self.write_config()
        with self.assertRaisesRegex(ValueError, "API key") as caught:
            load_provider_config(self.root)
        for source in ("env_key", "experimental_bearer_token", "auth.json", "OPENAI_API_KEY"):
            self.assertIn(source, str(caught.exception))

    def test_utf8_bom_config_and_auth_are_supported(self):
        self.write_config(encoding="utf-8-sig")
        (self.root / "auth.json").write_text(
            json.dumps({"OPENAI_API_KEY": "test-legacy-key"}), encoding="utf-8-sig"
        )
        self.assertEqual(load_provider_config(self.root).api_key, "test-legacy-key")

    def test_wrong_type_provider_secret_is_rejected_without_echo(self):
        self.write_config('experimental_bearer_token = ["test-sensitive-value"]\n')
        with self.assertRaisesRegex(ValueError, "experimental_bearer_token") as caught:
            load_provider_config(self.root)
        self.assertNotIn("test-sensitive-value", str(caught.exception))

    def test_missing_provider_configuration_is_rejected(self):
        (self.root / "config.toml").write_text('model_provider = "missing"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Provider"):
            load_provider_config(self.root, api_key_override="test-key")

    def test_invalid_base_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTP|http"):
            load_provider_config(
                self.root, base_url_override="file:///private", api_key_override="test-key"
            )

    def test_configuration_files_are_not_modified(self):
        self.write_config('experimental_bearer_token = "test-provider-key"\n')
        self.write_auth({"OPENAI_API_KEY": "test-legacy-key"})
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        load_provider_config(self.root)
        after = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
