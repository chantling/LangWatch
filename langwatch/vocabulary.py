from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from langwatch.config import AnkiConfig
from langwatch.translator import LLMTranslator


@dataclass
class VocabEntry:
    word: str
    translation: str
    example: str
    pos: str


def extract_word_frequencies(transcript: str, min_length: int = 2) -> dict[str, int]:
    words = re.findall(r"\b\w+\b", transcript.lower())
    freq: dict[str, int] = {}
    for word in words:
        if len(word) < min_length:
            continue
        freq[word] = freq.get(word, 0) + 1
    return freq


def filter_by_frequency(
    frequencies: dict[str, int], min_frequency: int
) -> dict[str, int]:
    return {w: c for w, c in frequencies.items() if c >= min_frequency}


def export_anki_csv(entries: list[VocabEntry], filepath: Path, separator: str = "tab") -> Path:
    sep = "\t" if separator == "tab" else ";"

    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=sep, quoting=csv.QUOTE_ALL)
        for entry in entries:
            writer.writerow([entry.word, entry.translation, entry.example, entry.pos])

    return filepath


def generate_vocabulary(
    transcript: str,
    translator: LLMTranslator,
    anki_config: AnkiConfig,
    source_lang: str,
    target_lang: str,
    output_path: Path,
) -> Path | None:
    if not anki_config.enabled:
        return None

    frequencies = extract_word_frequencies(transcript)
    filtered = filter_by_frequency(frequencies, anki_config.min_frequency)

    if not filtered:
        return None

    curated = translator.curate_vocabulary(
        filtered,
        transcript,
        target_lang,
        source_lang,
        anki_config.max_words,
    )

    if not curated:
        return None

    entries = [
        VocabEntry(
            word=e.get("term", ""),
            translation=e.get("translation", ""),
            example=e.get("example", ""),
            pos=e.get("pos", ""),
        )
        for e in curated
    ]

    return export_anki_csv(entries, output_path, anki_config.separator)
