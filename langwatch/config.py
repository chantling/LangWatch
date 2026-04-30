from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    api_base: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "llama3"
    max_tokens_per_request: int = 4096
    temperature: float = 0.3
    translation_batch_size: int = 12
    gloss_batch_size: int = 20
    vocab_batch_size: int = 50
    max_retries: int = 2


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
            "api_base": "http://localhost:11434/v1",
            "api_key": "",
            "model": "llama3",
            "max_tokens_per_request": 4096,
            "temperature": 0.3,
            "translation_batch_size": 12,
            "gloss_batch_size": 20,
            "vocab_batch_size": 50,
            "max_retries": 2,
        },
        "anki": {
            "enabled": True,
            "separator": "tab",
            "min_frequency": 2,
            "max_words": 50,
        },
    }


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    defaults = _defaults_dict()

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        merged = _deep_merge(defaults, user_config)
    else:
        merged = defaults

    return _dict_to_config(merged)


def _dict_to_config(d: dict) -> AppConfig:
    llm_data = d.get("llm", {})
    anki_data = d.get("anki", {})

    return AppConfig(
        download_dir=d.get("download_dir", "./downloads"),
        video_resolution=int(d.get("video_resolution", 720)),
        source_language=d.get("source_language", "auto"),
        target_language=d.get("target_language", "en"),
        llm=LLMConfig(
            api_base=llm_data.get("api_base", "http://localhost:11434/v1"),
            api_key=llm_data.get("api_key", ""),
            model=llm_data.get("model", "llama3"),
            max_tokens_per_request=int(llm_data.get("max_tokens_per_request", 4096)),
            temperature=float(llm_data.get("temperature", 0.3)),
            translation_batch_size=int(llm_data.get("translation_batch_size", 12)),
            gloss_batch_size=int(llm_data.get("gloss_batch_size", 20)),
            vocab_batch_size=int(llm_data.get("vocab_batch_size", 50)),
            max_retries=int(llm_data.get("max_retries", 2)),
        ),
        anki=AnkiConfig(
            enabled=anki_data.get("enabled", True),
            separator=anki_data.get("separator", "tab"),
            min_frequency=int(anki_data.get("min_frequency", 2)),
            max_words=int(anki_data.get("max_words", 50)),
        ),
    )
