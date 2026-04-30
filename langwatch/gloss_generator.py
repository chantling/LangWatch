from __future__ import annotations

from pathlib import Path

from langwatch.caption_processor import parse_sentences
from langwatch.translator import LLMTranslator


def _align_columns(words: list[str], glosses: list[str]) -> tuple[str, str]:
    n = max(len(words), len(glosses))
    while len(words) < n:
        words.append("")
    while len(glosses) < n:
        glosses.append("")

    widths = [
        max(len(words[i].strip()), len(glosses[i].strip())) + 2
        for i in range(n)
    ]

    words_line = "".join(
        words[i].strip().ljust(widths[i]) for i in range(n)
    ).rstrip()
    glosses_line = "".join(
        glosses[i].strip().ljust(widths[i]) for i in range(n)
    ).rstrip()

    return words_line, glosses_line


def format_gloss(entries: list[dict]) -> str:
    blocks: list[str] = []
    for i, entry in enumerate(entries, start=1):
        words = list(entry.get("words", []))
        glosses = list(entry.get("glosses", []))
        translation = entry.get("translation", "")
        original = entry.get("original", "")

        if words and glosses:
            words_line, glosses_line = _align_columns(words, glosses)
            trans_text = translation.strip().strip("'\"")
            block = f"[{i}]\n{words_line}\n{glosses_line}\n'{trans_text}'"
        else:
            block = f"[{i}]\n{original}\n{translation}"

        blocks.append(block)

    return "\n\n".join(blocks) + "\n"


def generate_and_save_gloss(
    subtitles: list,
    translator: LLMTranslator,
    target_lang: str,
    source_lang: str,
    output_path: Path,
) -> Path:
    sentences = parse_sentences(subtitles)
    sentence_texts = [s["text"] for s in sentences]

    gloss_entries = translator.translate_gloss_batch(
        sentence_texts, target_lang, source_lang
    )

    if not gloss_entries:
        gloss_entries = [
            {
                "original": s,
                "words": s.split(),
                "glosses": ["[gloss unavailable]"] * len(s.split()),
                "translation": "[translation unavailable]",
            }
            for s in sentence_texts
        ]

    gloss_text = format_gloss(gloss_entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gloss_text)

    return output_path
