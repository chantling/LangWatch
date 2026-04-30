from __future__ import annotations

from pathlib import Path

from langwatch.caption_processor import parse_sentences
from langwatch.translator import LLMTranslator


def format_gloss(entries: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for i, entry in enumerate(entries, start=1):
        block = (
            f"[{i}]\n"
            f"{entry.get('original', '')}\n"
            f"{entry.get('gloss', '')}\n"
            f"{entry.get('translation', '')}\n"
        )
        blocks.append(block)

    return "\n".join(blocks)


def generate_and_save_gloss(
    subtitles: list,
    translator: LLMTranslator,
    target_lang: str,
    source_lang: str,
    output_path: Path,
) -> Path:
    sentences = parse_sentences(subtitles)
    sentence_texts = [s["text"] for s in sentences]

    gloss_entries = translator.translate_gloss_batch(sentence_texts, target_lang, source_lang)

    if not gloss_entries:
        gloss_entries = [
            {
                "original": s,
                "gloss": "[gloss unavailable]",
                "translation": "[translation unavailable]",
            }
            for s in sentence_texts
        ]

    gloss_text = format_gloss(gloss_entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gloss_text)

    return output_path
