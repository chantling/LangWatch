from __future__ import annotations

from pathlib import Path
from typing import List

import srt

from langwatch.translator import LLMTranslator


def save_original_srt(subtitles: List[srt.Subtitle], filepath: Path) -> Path:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    content = srt.compose(subtitles)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def generate_bilingual_srt(
    subtitles: List[srt.Subtitle],
    translations: List[str],
) -> str:
    result_subs: list[srt.Subtitle] = []

    for i, (sub, translation) in enumerate(zip(subtitles, translations), start=1):
        original_text = sub.content.replace("\n", " ").strip()
        content = f"{original_text}\n{translation}"

        result_subs.append(
            srt.Subtitle(
                index=i,
                start=sub.start,
                end=sub.end,
                content=content,
            )
        )

    return srt.compose(result_subs, reindex=False)


def save_srt(content: str, filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def translate_and_save_srt(
    subtitles: List[srt.Subtitle],
    translator: LLMTranslator,
    target_lang: str,
    source_lang: str,
    output_path: Path,
) -> Path:
    texts = [sub.content.replace("\n", " ").strip() for sub in subtitles]
    translations = translator.translate_subtitles(texts, target_lang, source_lang)

    bilingual_content = generate_bilingual_srt(subtitles, translations)
    save_srt(bilingual_content, output_path)

    return output_path
