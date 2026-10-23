from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

AUTH_FILE_NAME = "auth.json"
CONFIG_FILE_NAME = "config.toml"
KEY_FIELD = "OPENAI_API_KEY"


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str = field(repr=False)
    base_url: str
    codex_home: Path
    api_key_source: str = "unspecified"


def resolve_codex_home(explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()
    env_path = os.environ.get("CODEX_HOME")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in {path}; check the file syntax.") from None
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return data


def load_toml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError:
        raise ValueError(f"Invalid TOML in {path}; check the file syntax.") from None


def load_provider_config(
    codex_home: Path,
    base_url_override: str | None = None,
    api_key_override: str | None = None,
    api_key_env: str | None = None,
) -> ProviderConfig:
    override_api_key = resolve_api_key_override(api_key_override, api_key_env)
    config_path = codex_home / CONFIG_FILE_NAME
    provider: dict = {}
    if base_url_override is None or override_api_key is None:
        if config_path.exists() or base_url_override is None:
            config = load_toml(config_path)
            provider = active_provider(config, config_path, required=base_url_override is None)

    base_url = base_url_override if base_url_override is not None else provider.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url is missing in config or --base-url.")
    base_url = normalize_base_url(base_url)

    if override_api_key is not None:
        api_key = override_api_key
        source = "--api-key-env" if api_key_env is not None else "--api-key"
    else:
        api_key, source = resolve_configured_api_key(provider, codex_home)
    return ProviderConfig(
        api_key=api_key, base_url=base_url, codex_home=codex_home, api_key_source=source
    )


def active_provider(config: dict, config_path: Path, required: bool) -> dict:
    provider_name = config.get("model_provider")
    if not provider_name:
        if required:
            raise ValueError(f"model_provider is missing in {config_path}")
        return {}
    if not isinstance(provider_name, str):
        raise ValueError(f"model_provider must be a string in {config_path}.")
    providers = config.get("model_providers", {})
    provider = providers.get(provider_name) if isinstance(providers, dict) else None
    if provider is None and not required:
        return {}
    if not isinstance(provider, dict):
        raise ValueError(f"Provider '{provider_name}' is missing in {config_path}")
    return provider


def resolve_configured_api_key(provider: dict, codex_home: Path) -> tuple[str, str]:
    env_name = optional_string(provider, "env_key", "active provider")
    if env_name is not None:
        api_key = os.environ.get(env_name, "").strip()
        if not api_key:
            raise ValueError(
                f"Provider env_key environment variable '{env_name}' is empty or not set. "
                "Set it or use --api-key-env; no other credential was selected."
            )
        return api_key, "active provider env_key"

    bearer_token = optional_string(provider, "experimental_bearer_token", "active provider")
    if bearer_token is not None:
        return bearer_token, "active provider experimental_bearer_token"

    auth_path = codex_home / AUTH_FILE_NAME
    if auth_path.exists():
        auth = load_json(auth_path)
        api_key = optional_string(auth, KEY_FIELD, "auth.json")
        if api_key is not None:
            return api_key, "auth.json OPENAI_API_KEY"

    api_key = os.environ.get(KEY_FIELD, "").strip()
    if api_key:
        return api_key, "environment OPENAI_API_KEY"

    raise ValueError(
        "No image API key found. Use --api-key-env, the active provider's env_key or "
        "experimental_bearer_token, auth.json OPENAI_API_KEY, or the OPENAI_API_KEY "
        "environment variable. auth.json is optional when another source is configured. "
        "ChatGPT login/OAuth and OS keyring credentials are not read by this script; "
        "supply an API key accepted by the selected image provider."
    )


def optional_string(values: dict, key: str, source: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source} {key} must be a non-empty string.")
    return value.strip()


def resolve_api_key_override(api_key_override: str | None, api_key_env: str | None) -> str | None:
    if api_key_override is not None and api_key_env is not None:
        raise ValueError("Use only one of --api-key or --api-key-env.")
    if api_key_override is not None:
        api_key = api_key_override.strip()
        if not api_key:
            raise ValueError("--api-key must not be empty.")
        return api_key
    if api_key_env is not None:
        env_name = api_key_env.strip()
        if not env_name:
            raise ValueError("--api-key-env must name a non-empty environment variable.")
        api_key = os.environ.get(env_name, "").strip()
        if not api_key:
            raise ValueError(f"Environment variable '{env_name}' is empty or not set.")
        return api_key
    return None


def normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("--base-url must not be empty.")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("--base-url must start with http:// or https://.")
    return normalized
