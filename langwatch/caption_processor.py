from __future__ import annotations

from pathlib import Path
from typing import List

import srt


def deduplicate_subtitles(subtitles: List[srt.Subtitle]) -> List[srt.Subtitle]:
    if not subtitles:
        return []

    deduped: list[srt.Subtitle] = []
    previous_text_clean = ""

    for sub in subtitles:
        current_text_clean = sub.content.strip()
        if not current_text_clean:
            if deduped:
                deduped[-1] = srt.Subtitle(
                    index=deduped[-1].index,
                    start=deduped[-1].start,
                    end=sub.end,
                    content=deduped[-1].content,
                )
            continue

        current_lines = [line.strip() for line in current_text_clean.split("\n") if line.strip()]

        if not deduped:
            new_sub = srt.Subtitle(
                index=1,
                start=sub.start,
                end=sub.end,
                content=current_text_clean,
            )
            deduped.append(new_sub)
            previous_text_clean = current_text_clean
            continue

        if current_text_clean == previous_text_clean:
            deduped[-1] = srt.Subtitle(
                index=deduped[-1].index,
                start=deduped[-1].start,
                end=sub.end,
                content=deduped[-1].content,
            )
            continue

        if current_lines and current_lines[0] == previous_text_clean:
            new_content = "\n".join(current_lines[1:]) if len(current_lines) > 1 else ""
            if new_content:
                new_sub = srt.Subtitle(
                    index=len(deduped) + 1,
                    start=sub.start,
                    end=sub.end,
                    content=new_content,
                )
                deduped.append(new_sub)
                previous_text_clean = new_content
            continue

        if "\n" in current_text_clean:
            if current_lines[0] == previous_text_clean:
                new_content = "\n".join(current_lines[1:])
                if new_content:
                    new_sub = srt.Subtitle(
                        index=len(deduped) + 1,
                        start=sub.start,
                        end=sub.end,
                        content=new_content,
                    )
                    deduped.append(new_sub)
                    previous_text_clean = new_content
            else:
                deduped.append(sub)
                previous_text_clean = current_text_clean
        else:
            deduped.append(sub)
            previous_text_clean = current_text_clean

    result = []
    idx = 1
    for sub in deduped:
        if sub.content.strip():
            result.append(srt.Subtitle(
                index=idx,
                start=sub.start,
                end=sub.end,
                content=sub.content.strip(),
            ))
            idx += 1

    return result


def process_captions(srt_path: Path) -> list[srt.Subtitle]:
    with open(srt_path, "r", encoding="utf-8") as f:
        raw_content = f.read()
    subtitles = list(srt.parse(raw_content))
    return deduplicate_subtitles(subtitles)


def parse_transcript(subtitles: list[srt.Subtitle]) -> str:
    return " ".join(s.content.replace("\n", " ") for s in subtitles)


def parse_sentences(subtitles: list[srt.Subtitle]) -> list[dict]:
    sentences: list[dict] = []
    current_text = ""
    current_start = None
    current_end = None

    for sub in subtitles:
        text = sub.content.replace("\n", " ").strip()
        if not text:
            continue

        if current_start is None:
            current_start = sub.start
        current_end = sub.end

        if current_text:
            current_text += " " + text
        else:
            current_text = text

        if text and text[-1] in ".!?":
            sentences.append({
                "text": current_text.strip(),
                "start": current_start,
                "end": current_end,
            })
            current_text = ""
            current_start = None
            current_end = None

    if current_text.strip():
        sentences.append({
            "text": current_text.strip(),
            "start": current_start,
            "end": current_end,
        })

    return sentences
