from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from openai import OpenAI

from langwatch.config import LLMApiConfig

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 3


class LLMTranslator:
    def __init__(self, api_config: LLMApiConfig):
        self.api_config = api_config
        self.client = OpenAI(
            base_url=api_config.api_base,
            api_key=api_config.api_key or "not-needed",
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.api_config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.api_config.max_tokens_per_request,
            temperature=self.api_config.temperature,
        )
        return response.choices[0].message.content.strip()

    def _call_with_retry(
        self, system_prompt: str, user_prompt: str, validator: Optional[callable] = None
    ) -> str:
        last_error = None
        for attempt in range(self.api_config.max_retries + 1):
            try:
                result = self._call_llm(system_prompt, user_prompt)
                if validator and not validator(result):
                    raise ValueError("Validation failed for LLM response")
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt < self.api_config.max_retries:
                    time.sleep(1 * (attempt + 1))
        raise last_error

    def _calculate_batch_size(
        self,
        entries: list[str],
        system_prompt: str,
        output_multiplier: float = 1.5,
        output_per_entry: Optional[int] = None,
    ) -> int:
        if not entries:
            return 0

        system_tokens = len(system_prompt) // CHARS_PER_TOKEN
        avg_input = (
            sum(len(e) for e in entries) / max(len(entries), 1) / CHARS_PER_TOKEN + 5
        )

        if output_per_entry is not None:
            avg_output = output_per_entry
        else:
            avg_output = avg_input * output_multiplier

        tokens_per_entry = avg_input + avg_output
        available = self.api_config.max_context_window - system_tokens

        if tokens_per_entry <= 0:
            return len(entries)

        max_by_context = int(available / tokens_per_entry)
        max_by_output = int(
            self.api_config.max_tokens_per_request / max(avg_output, 1)
        )

        return max(1, min(len(entries), max_by_context, max_by_output))

    def _process_concurrent(
        self, batches: list, process_fn, max_workers: int = 4
    ) -> list:
        if len(batches) <= 1:
            return [process_fn(batches[0])] if batches else []

        results: list = [None] * len(batches)
        with ThreadPoolExecutor(max_workers=min(len(batches), max_workers)) as executor:
            futures = {
                executor.submit(process_fn, batch): i
                for i, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.warning(f"Batch {idx} failed: {e}")
                    results[idx] = None

        return results

    def translate_subtitles(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[str]:
        if not texts:
            return []

        system_prompt = (
            f"You are a professional translator. Translate the following numbered subtitle lines "
            f"from {source_lang} to {target_lang}. "
            f"Return ONLY the translations, one per line, using the same numbering format: "
            f"'1. translation here'. "
            f"Do not add any preamble, explanation, or extra text. "
            f"Preserve the meaning and natural flow of the subtitles."
        )

        batch_size = self._calculate_batch_size(
            texts, system_prompt, output_multiplier=1.0
        )
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        if len(batches) == 1:
            result = self._translate_batch(batches[0], target_lang, source_lang)
            return result

        batch_results = self._process_concurrent(
            batches,
            lambda batch: self._translate_batch(batch, target_lang, source_lang),
        )

        all_translations: list[str] = []
        for i, batch_result in enumerate(batch_results):
            if batch_result is not None:
                all_translations.extend(batch_result)
            else:
                fallback = self._translate_individual(
                    batches[i], target_lang, source_lang
                )
                all_translations.extend(fallback)

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

        def validate(response: str) -> bool:
            parsed = _parse_numbered_response(response)
            return len(parsed) == expected_count

        try:
            response = self._call_with_retry(system_prompt, numbered_input, validate)
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
    ) -> list[dict[str, str | list[str]]]:
        if not sentences:
            return []

        system_prompt = _gloss_system_prompt(target_lang, source_lang)

        batch_size = self._calculate_batch_size(
            sentences, system_prompt, output_multiplier=2.5
        )
        batches = [
            sentences[i : i + batch_size]
            for i in range(0, len(sentences), batch_size)
        ]

        if len(batches) == 1:
            return self._gloss_batch(batches[0], target_lang, source_lang)

        batch_results = self._process_concurrent(
            batches,
            lambda batch: self._gloss_batch(batch, target_lang, source_lang),
        )

        all_results: list[dict] = []
        for i, batch_result in enumerate(batch_results):
            if batch_result is not None:
                all_results.extend(batch_result)
            else:
                all_results.extend(
                    [
                        {
                            "original": s,
                            "words": s.split(),
                            "glosses": ["[gloss failed]"] * len(s.split()),
                            "translation": "[translation failed]",
                        }
                        for s in batches[i]
                    ]
                )

        return all_results

    def _gloss_batch(
        self, sentences: list[str], target_lang: str, source_lang: str
    ) -> list[dict[str, str | list[str]]]:
        expected_count = len(sentences)
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
        system_prompt = _gloss_system_prompt(target_lang, source_lang)

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
                "words": s.split(),
                "glosses": ["[gloss failed]"] * len(s.split()),
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

        words_list = list(word_frequencies.keys())

        system_prompt = _vocab_system_prompt(target_lang, source_lang, max_words)
        batch_size = self._calculate_batch_size(
            words_list, system_prompt, output_per_entry=60
        )

        batches = [
            words_list[i : i + batch_size]
            for i in range(0, len(words_list), batch_size)
        ]

        all_results: list[dict[str, str]] = []
        remaining = max_words

        if len(batches) == 1:
            batch_freq = {w: word_frequencies[w] for w in batches[0]}
            results = self._vocab_batch(
                batch_freq, transcript, target_lang, source_lang, remaining
            )
            all_results.extend(results)
        else:
            batch_results = self._process_concurrent(
                batches,
                lambda batch: self._vocab_batch(
                    {w: word_frequencies[w] for w in batch},
                    transcript,
                    target_lang,
                    source_lang,
                    remaining,
                ),
            )
            for batch_result in batch_results:
                if batch_result:
                    all_results.extend(batch_result)
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
        words_with_freq = "\n".join(
            f"  {w} (appears {c}x)" for w, c in word_frequencies.items()
        )
        context = transcript[:3000]
        system_prompt = _vocab_system_prompt(target_lang, source_lang, max_words)
        user_prompt = f"Transcript context:\n{context}\n\nWords to select from:\n{words_with_freq}"

        try:
            response = self._call_with_retry(system_prompt, user_prompt)
            return _parse_vocab_entries(response)
        except Exception as e:
            logger.warning(f"Vocabulary curation failed: {e}")
            return []


def _gloss_system_prompt(target_lang: str, source_lang: str) -> str:
    return (
        f"You are a linguistic glossing assistant. For each sentence in {source_lang}, "
        f"provide a word-by-word morphological gloss following Leipzig Glossing Rules "
        f"and a free translation in {target_lang}.\n\n"
        f"For each numbered sentence, return EXACTLY this format:\n"
        f"<entry>\n"
        f"original: [the original sentence]\n"
        f"words: word1 | word2 | word3\n"
        f"glosses: gloss1 | gloss2 | gloss3\n"
        f"translation: free translation here\n"
        f"</entry>\n\n"
        f"Glossing rules:\n"
        f"- Split each sentence into its constituent words, keeping punctuation attached to the preceding word\n"
        f"- For each word, provide a morphological gloss:\n"
        f"  * Use UPPERCASE for grammatical labels: person (1SG, 2SG, 3SG, 1PL, 2PL, 3PL), "
        f"number (SG, PL), gender (MASC, FEM, NEUT), case (NOM, ACC, DAT, GEN), "
        f"tense (PRS, PST, FUT), mood (IND, SUBJ, IMP), aspect (PFV, IPFV, PROG), "
        f"voice (ACT, PASS, MID), definiteness (DEF, INDF), etc.\n"
        f"  * Use lowercase for semantic translations of content words\n"
        f"  * Separate morphemes within a word with periods: e.g. habl.3SG.PRS\n"
        f"  * Proper nouns (names, brands) keep their original form as the gloss\n"
        f"- The number of items in 'words' and 'glosses' must match exactly\n"
        f"- The free translation should be natural and idiomatic\n\n"
        f"Do not add any text outside of the <entry> blocks."
    )


def _vocab_system_prompt(target_lang: str, source_lang: str, max_words: int) -> str:
    return (
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


def _parse_gloss_entries(response: str) -> list[dict]:
    entries: list[dict] = []
    blocks = re.findall(r"<entry>(.*?)</entry>", response, re.DOTALL)

    for block in blocks:
        entry: dict = {}

        match = re.search(r"original:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL)
        entry["original"] = match.group(1).strip() if match else ""

        match = re.search(r"words:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL)
        if match:
            entry["words"] = [w.strip() for w in match.group(1).strip().split("|")]
        else:
            entry["words"] = []

        match = re.search(r"glosses:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL)
        if match:
            entry["glosses"] = [g.strip() for g in match.group(1).strip().split("|")]
        else:
            entry["glosses"] = []

        match = re.search(r"translation:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL)
        entry["translation"] = match.group(1).strip() if match else ""

        if entry.get("original"):
            entries.append(entry)

    return entries


def _parse_vocab_entries(response: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    blocks = re.findall(r"<word>(.*?)</word>", response, re.DOTALL)

    for block in blocks:
        entry: dict[str, str] = {}
        for field_name in ("term", "translation", "example", "pos"):
            match = re.search(
                rf"{field_name}:\s*(.+?)(?=\n\w+:|$)", block, re.DOTALL
            )
            if match:
                entry[field_name] = match.group(1).strip()
            else:
                entry[field_name] = ""

        if entry.get("term"):
            entries.append(entry)

    return entries
