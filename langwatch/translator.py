from __future__ import annotations

import logging
import re
import time
from typing import Any

from openai import OpenAI

from langwatch.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMTranslator:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = OpenAI(
            base_url=config.api_base,
            api_key=config.api_key or "not-needed",
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.config.max_tokens_per_request,
            temperature=self.config.temperature,
        )
        return response.choices[0].message.content.strip()

    def _call_with_retry(
        self, system_prompt: str, user_prompt: str, validator: callable | None = None
    ) -> str:
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                result = self._call_llm(system_prompt, user_prompt)
                if validator and not validator(result):
                    raise ValueError(f"Validation failed for LLM response")
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries:
                    time.sleep(1 * (attempt + 1))
        raise last_error

    def translate_subtitles(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[str]:
        if not texts:
            return []

        batch_size = self.config.translation_batch_size
        all_translations: list[str] = []

        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        for batch in batches:
            translations = self._translate_batch(batch, target_lang, source_lang)
            all_translations.extend(translations)

        return all_translations

    def _translate_batch(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[str]:
        expected_count = len(texts)

        numbered_input = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))

        system_prompt = (
            f"You are a professional translator. Translate the following numbered subtitle lines "
            f"from {source_lang} to {target_lang}. "
            f"Return ONLY the translations, one per line, using the same numbering format: "
            f"'1. translation here'. "
            f"Do not add any preamble, explanation, or extra text. "
            f"Preserve the meaning and natural flow of the subtitles."
        )

        user_prompt = numbered_input

        def validate(response: str) -> bool:
            parsed = _parse_numbered_response(response)
            return len(parsed) == expected_count

        try:
            response = self._call_with_retry(system_prompt, user_prompt, validate)
            translations = _parse_numbered_response(response)
            if len(translations) == expected_count:
                return translations
        except Exception as e:
            logger.warning(f"Batch translation failed: {e}. Falling back to individual.")

        return self._translate_individual(texts, target_lang, source_lang)

    def _translate_individual(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[str]:
        translations = []
        for text in texts:
            system_prompt = (
                f"You are a professional translator. Translate the following text "
                f"from {source_lang} to {target_lang}. "
                f"Return ONLY the translation, nothing else."
            )
            try:
                result = self._call_with_retry(system_prompt, text)
                translations.append(result)
            except Exception:
                logger.warning(f"Failed to translate: {text[:50]}...")
                translations.append(f"[Translation failed] {text}")
        return translations

    def translate_gloss_batch(
        self, sentences: list[str], target_lang: str, source_lang: str
    ) -> list[dict[str, str]]:
        if not sentences:
            return []

        batch_size = self.config.gloss_batch_size
        all_results: list[dict[str, str]] = []

        batches = [
            sentences[i : i + batch_size] for i in range(0, len(sentences), batch_size)
        ]

        for batch in batches:
            results = self._gloss_batch(batch, target_lang, source_lang)
            all_results.extend(results)

        return all_results

    def _gloss_batch(
        self, sentences: list[str], target_lang: str, source_lang: str
    ) -> list[dict[str, str]]:
        expected_count = len(sentences)

        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))

        system_prompt = (
            f"You are a linguistic glossing assistant. For each numbered sentence in {source_lang}, "
            f"provide a word-by-word gloss in {target_lang} and a full free translation.\n\n"
            f"Return your response in this EXACT format for EACH sentence:\n"
            f"<entry>\n"
            f"original: [original sentence]\n"
            f"gloss: [word-by-word translation, preserving word order]\n"
            f"translation: [natural free translation]\n"
            f"</entry>\n\n"
            f"Do not add any other text. Process all {expected_count} sentences."
        )

        def validate(response: str) -> bool:
            entries = _parse_gloss_entries(response)
            return len(entries) == expected_count

        try:
            response = self._call_with_retry(system_prompt, numbered, validate)
            entries = _parse_gloss_entries(response)
            if len(entries) == expected_count:
                return entries
        except Exception as e:
            logger.warning(f"Gloss batch failed: {e}")

        return [
            {
                "original": s,
                "gloss": "[gloss failed]",
                "translation": "[translation failed]",
            }
            for s in sentences
        ]

    def curate_vocabulary(
        self,
        word_frequencies: dict[str, int],
        transcript: str,
        target_lang: str,
        source_lang: str,
        max_words: int,
    ) -> list[dict[str, str]]:
        if not word_frequencies:
            return []

        batch_size = self.config.vocab_batch_size
        words_list = list(word_frequencies.keys())
        all_results: list[dict[str, str]] = []

        batches = [
            words_list[i : i + batch_size] for i in range(0, len(words_list), batch_size)
        ]

        for batch in batches:
            batch_freq = {w: word_frequencies[w] for w in batch}
            results = self._vocab_batch(batch_freq, transcript, target_lang, source_lang, max_words)
            all_results.extend(results)
            remaining = max_words - len(all_results)
            if remaining <= 0:
                break

        return all_results[:max_words]

    def _vocab_batch(
        self,
        word_frequencies: dict[str, int],
        transcript: str,
        target_lang: str,
        source_lang: str,
        max_words: int,
    ) -> list[dict[str, str]]:
        words_with_freq = "\n".join(f"  {w} (appears {c}x)" for w, c in word_frequencies.items())

        context = transcript[:3000]

        system_prompt = (
            f"You are a language learning assistant. Given a list of {source_lang} words from a transcript, "
            f"select up to {max_words} words that are most useful for a language learner to study. "
            f"Prefer less common, content-bearing words over function words (articles, prepositions, etc.).\n\n"
            f"For each selected word, provide:\n"
            f"- The word (as it appears)\n"
            f"- Its translation to {target_lang}\n"
            f"- An example sentence from the transcript where the word appears (or a shortened portion)\n"
            f"- Its part of speech (noun, verb, adjective, adverb, etc.)\n\n"
            f"Return your response in this EXACT format for EACH word:\n"
            f"<word>\n"
            f"term: [word]\n"
            f"translation: [translation]\n"
            f"example: [example sentence]\n"
            f"pos: [part of speech]\n"
            f"</word>\n\n"
            f"Do not add any other text."
        )

        user_prompt = f"Transcript context:\n{context}\n\nWords to select from:\n{words_with_freq}"

        try:
            response = self._call_with_retry(system_prompt, user_prompt)
            return _parse_vocab_entries(response)
        except Exception as e:
            logger.warning(f"Vocabulary curation failed: {e}")
            return []


def _parse_numbered_response(response: str) -> list[str]:
    lines = response.strip().split("\n")
    results: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\d+\.\s*(.*)", line)
        if match:
            results.append(match.group(1).strip())
        elif results:
            results[-1] += " " + line
        else:
            results.append(line)

    return results


def _parse_gloss_entries(response: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    blocks = re.findall(r"<entry>(.*?)</entry>", response, re.DOTALL)

    for block in blocks:
        entry: dict[str, str] = {}
        for field_name in ("original", "gloss", "translation"):
            match = re.search(rf"{field_name}:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL)
            if match:
                entry[field_name] = match.group(1).strip()
            else:
                entry[field_name] = ""

        if entry.get("original"):
            entries.append(entry)

    return entries


def _parse_vocab_entries(response: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    blocks = re.findall(r"<word>(.*?)</word>", response, re.DOTALL)

    for block in blocks:
        entry: dict[str, str] = {}
        for field_name in ("term", "translation", "example", "pos"):
            match = re.search(rf"{field_name}:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL)
            if match:
                entry[field_name] = match.group(1).strip()
            else:
                entry[field_name] = ""

        if entry.get("term"):
            entries.append(entry)

    return entries
