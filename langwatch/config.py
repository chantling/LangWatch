from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMApiConfig:
    api_base: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "llama3"
    max_context_window: int = 8192
    max_tokens_per_request: int = 4096
    temperature: float = 0.3
    max_retries: int = 2


@dataclass
class LLMConfig:
    active: str = "default"
    apis: dict[str, LLMApiConfig] = field(
        default_factory=lambda: {"default": LLMApiConfig()}
    )

    def get_active_api(self) -> LLMApiConfig:
        if self.active in self.apis:
            return self.apis[self.active]
        if self.apis:
            return next(iter(self.apis.values()))
        return LLMApiConfig()


@dataclass
class AnkiConfig:
    enabled: bool = True
    separator: str = "tab"
    min_frequency: int = 2
    max_words: int = 50


@dataclass
class AppConfig:
    download_dir: str = "./downloads"
    video_resolution: int = 720
    source_language: str = "auto"
    target_language: str = "en"
    llm: LLMConfig = field(default_factory=LLMConfig)
    anki: AnkiConfig = field(default_factory=AnkiConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _defaults_dict() -> dict:
    return {
        "download_dir": "./downloads",
        "video_resolution": 720,
        "source_language": "auto",
        "target_language": "en",
        "llm": {
            "active": "default",
            "apis": {
                "default": {
                    "api_base": "http://localhost:11434/v1",
                    "api_key": "",
                    "model": "llama3",
                    "max_context_window": 8192,
                    "max_tokens_per_request": 4096,
                    "temperature": 0.3,
                    "max_retries": 2,
                },
            },
        },
        "anki": {
            "enabled": True,
            "separator": "tab",
            "min_frequency": 2,
            "max_words": 50,
        },
    }


def _parse_api_config(data: dict) -> LLMApiConfig:
    return LLMApiConfig(
        api_base=data.get("api_base", "http://localhost:11434/v1"),
        api_key=data.get("api_key", ""),
        model=data.get("model", "llama3"),
        max_context_window=int(data.get("max_context_window", 8192)),
        max_tokens_per_request=int(data.get("max_tokens_per_request", 4096)),
        temperature=float(data.get("temperature", 0.3)),
        max_retries=int(data.get("max_retries", 2)),
    )


def _is_old_llm_format(llm_data: dict) -> bool:
    return "apis" not in llm_data and (
        "api_base" in llm_data or "model" in llm_data
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    defaults = _defaults_dict()

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        merged = _deep_merge(defaults, user_config)
    else:
        merged = defaults

    return _dict_to_config(merged, user_config if config_path.exists() else {})


def _dict_to_config(d: dict, user_config: dict = {}) -> AppConfig:
    llm_data = d.get("llm", {})
    anki_data = d.get("anki", {})

    user_llm = user_config.get("llm", {}) if user_config else {}
    if _is_old_llm_format(user_llm):
        api_config = _parse_api_config(llm_data)
        llm_config = LLMConfig(active="default", apis={"default": api_config})
    else:
        active = llm_data.get("active", "default")
        user_apis = user_llm.get("apis")
        if user_apis:
            apis = {name: _parse_api_config(cfg) for name, cfg in user_apis.items()}
        else:
            apis_data = llm_data.get("apis", {})
            apis = {name: _parse_api_config(cfg) for name, cfg in apis_data.items()}
        if not apis:
            apis = {"default": LLMApiConfig()}
        llm_config = LLMConfig(active=active, apis=apis)

    return AppConfig(
        download_dir=d.get("download_dir", "./downloads"),
        video_resolution=int(d.get("video_resolution", 720)),
        source_language=d.get("source_language", "auto"),
        target_language=d.get("target_language", "en"),
        llm=llm_config,
        anki=AnkiConfig(
            enabled=anki_data.get("enabled", True),
            separator=anki_data.get("separator", "tab"),
            min_frequency=int(anki_data.get("min_frequency", 2)),
            max_words=int(anki_data.get("max_words", 50)),
        ),
    )
