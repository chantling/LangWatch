# LangWatch

A command-line tool for language learners that downloads videos with captions, generates bilingual subtitles, word-by-word glosses, and Anki flashcard decks — all from a single URL.

## Overview

LangWatch takes a video URL (YouTube or any yt-dlp supported site), downloads the video and its captions, and produces a set of learning materials:

1. **Video** — Downloaded at your preferred resolution
2. **Bilingual subtitles** — SRT file with the original language on top and your target language below, ready for VLC or any media player
3. **Interlinear gloss** — Word-by-word translation of each sentence for reading practice
4. **Anki vocabulary deck** — CSV file with curated vocabulary words, translations, example sentences, and parts of speech, ready for Anki import

All files are saved together with a consistent naming convention:

```
downloads/
├── 2026-04-26 - Beginner Spanish Discovering Korea's Most Modern District!.mp4
├── 2026-04-26 - Beginner Spanish Discovering Korea's Most Modern District!.srt
├── 2026-04-26 - Beginner Spanish Discovering Korea's Most Modern District!.txt
└── 2026-04-26 - Beginner Spanish Discovering Korea's Most Modern District!.csv
```

## Features

- **Bilingual subtitles** — Original language text on the first line, your language translation on the second line, displayed simultaneously in any media player
- **Rolling caption deduplication** — Automatically fixes YouTube's scrolling auto-generated captions that contain duplicate/overlapping lines
- **Smart language selection** — Prefers manual captions over auto-generated; detects language from video metadata; prompts interactively when there's a mismatch or ambiguity
- **Word-by-word interlinear gloss** — Each sentence shown with a word-by-word translation and a free translation below it, formatted for reading practice
- **LLM-curated Anki export** — Vocabulary words are filtered by frequency, then curated by an LLM that selects the most useful words and provides translations, example sentences from the transcript, and parts of speech
- **Configurable LLM backend** — Works with any OpenAI-compatible API: Ollama, OpenAI, LM Studio, vLLM, and others
- **Progress bars** — Visual progress for each pipeline step using rich
- **Interactive mode** — Process multiple URLs in a session without restarting
- **Graceful fallbacks** — If batch LLM translation fails, falls back to individual translations; if the LLM is unavailable for gloss/vocab, saves what it can

## Prerequisites

- **Python 3.10 or later**
- **[ffmpeg](https://ffmpeg.org/download.html)** — Required for video format conversion and caption extraction. Must be on your system PATH.
- **An OpenAI-compatible LLM** — One of:
  - [Ollama](https://ollama.ai) (local, free)
  - [OpenAI API](https://platform.openai.com)
  - [LM Studio](https://lmstudio.ai) (local, free)
  - Any other server implementing the OpenAI chat completions API

## Installation

```bash
git clone <repo-url> langwatch
cd langwatch
pip install -e .
```

Then copy the example config and edit it:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` to set your LLM endpoint, target language, and preferences. See the [Configuration](#configuration) section below.

## Configuration

All settings live in `config.yaml`. Copy `config.example.yaml` to get started.

### General Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `download_dir` | `"./downloads"` | Directory where all output files are saved |
| `video_resolution` | `720` | Maximum video resolution to download (e.g. `480`, `720`, `1080`, `2160`) |
| `source_language` | `"auto"` | Default caption language. Use `"auto"` to detect from video metadata, or an ISO 639-1 code like `"de"`, `"es"`, `"fr"` |
| `target_language` | `"en"` | Your native/study language for translations and glosses (ISO 639-1 code) |

### LLM Settings

These control how LangWatch communicates with your LLM for translations, glosses, and vocabulary curation.

| Setting | Default | Description |
|---------|---------|-------------|
| `llm.api_base` | `"http://localhost:11434/v1"` | OpenAI-compatible API base URL |
| `llm.api_key` | `""` | API key (leave empty for local models like Ollama) |
| `llm.model` | `"llama3"` | Model name to use |
| `llm.max_tokens_per_request` | `4096` | Maximum tokens per API request |
| `llm.temperature` | `0.3` | Sampling temperature. Lower values produce more consistent translations |
| `llm.translation_batch_size` | `12` | Number of subtitle entries translated per API call. Higher = faster but uses more tokens |
| `llm.gloss_batch_size` | `20` | Number of sentences glossed per API call |
| `llm.vocab_batch_size` | `50` | Number of vocabulary words analyzed per API call |
| `llm.max_retries` | `2` | Retries on LLM response parse failure before falling back to slower individual processing |

**Common `api_base` values:**

| Provider | `api_base` |
|----------|-----------|
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| OpenAI | `https://api.openai.com/v1` |

### Anki Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `anki.enabled` | `true` | Set to `false` to skip Anki CSV generation entirely |
| `anki.separator` | `"tab"` | Field separator in the CSV file: `"tab"` or `"semicolon"` |
| `anki.min_frequency` | `2` | A word must appear at least this many times in the transcript to be considered for the vocabulary list. Filters out rare/hapax words before LLM curation |
| `anki.max_words` | `50` | Maximum number of vocabulary cards to export |

## Usage

### Quick Start

Process a single video and exit:

```bash
python -m langwatch https://www.youtube.com/watch?v=VIDEO_ID
```

Or using the installed command:

```bash
langwatch https://www.youtube.com/watch?v=VIDEO_ID
```

### Interactive Mode

Run without a URL to enter interactive mode, where you can process multiple videos in sequence:

```bash
python -m langwatch
```

```
LangWatch - Language Learning Video Downloader
Type a video URL to download, or 'exit'/'quit' to quit.

Enter video URL (or 'exit' to quit): https://www.youtube.com/watch?v=abc123
  ... processing ...
Done!

Enter video URL (or 'exit' to quit): https://www.youtube.com/watch?v=def456
  ... processing ...
Done!

Enter video URL (or 'exit' to quit): exit
Goodbye!
```

### Command-Line Flags

| Flag | Description |
|------|-------------|
| `url` | Video URL to process (positional, optional) |
| `--config PATH` | Path to config.yaml (default: `./config.yaml`) |
| `--resolution N` | Override video resolution for this run (e.g. `1080`, `480`) |
| `--source-language CODE` | Force caption language (e.g. `de`, `es`, `fr`). Prompts if unavailable |
| `--target-language CODE` | Override target/translation language for this run |
| `--no-anki` | Skip Anki CSV export |
| `--no-gloss` | Skip gloss generation |
| `--no-subtitles` | Skip bilingual subtitle generation |

**Examples:**

```bash
# Force Spanish captions, output English glosses
python -m langwatch URL --source-language es --target-language en

# Download at 1080p, skip Anki and gloss
python -m langwatch URL --resolution 1080 --no-anki --no-gloss

# Use a different config file
python -m langwatch URL --config ~/my-config.yaml
```

### Language Selection

LangWatch uses a priority chain to determine which caption language to download:

1. **`--source-language` flag** — If provided, uses that language. If it's not available, shows available languages and prompts you to pick one.
2. **`source_language` in config** — If set to a specific code (not `"auto"`), uses that language. If video metadata disagrees (e.g. config says `de` but the video is in `es`), warns you and prompts. If the language isn't available, prompts.
3. **Auto-detection** — Uses the language from video metadata. If detection fails or the language isn't in the available captions, prompts.

Manual captions are always preferred over auto-generated when available for the selected language.

## Output Files

Each video produces up to four files, all with the same base name in the download directory:

### Video (`.mp4`)

The downloaded video file, converted to MP4 format. Resolution is capped at the configured `video_resolution`.

### Bilingual Subtitles (`.srt`)

A standard SRT subtitle file. Each entry contains two lines:

```
1
00:00:01,000 --> 00:00:04,000
Hola, yo soy Shell de Dreaming Spanish.
Hello, I'm Shell from Dreaming Spanish.
```

The first line is the original caption text; the second is the translation. This displays correctly in VLC, mpv, and other players that support multiline subtitles. Load it alongside the video in your player.

### Interlinear Gloss (`.txt`)

A word-by-word gloss of the transcript, organized by sentence:

```
[1]
Hola, yo soy Shell de Dreaming Spanish.
Hello, I am Shell of Dreaming Spanish.
Hello, I'm Shell from Dreaming Spanish.

[2]
Hoy estoy en Seul.
Today am I in Seoul.
Today I am in Seoul.
```

Each numbered block contains:
- **Original sentence** — The source language text
- **Gloss line** — Word-by-word translation preserving the original word order
- **Free translation** — Natural, fluent translation

### Anki Vocabulary (`.csv`)

A tab-separated (or semicolon-separated) CSV file with four columns:

| Column | Content |
|--------|---------|
| Word | The vocabulary word in the source language |
| Translation | Translation in your target language |
| Example Sentence | A sentence from the transcript containing the word |
| Part of Speech | Noun, verb, adjective, etc. |

The vocabulary selection process:
1. All words in the transcript are counted by frequency
2. Words appearing fewer than `min_frequency` times are filtered out
3. The remaining words are sent to the LLM, which selects up to `max_words` of the most useful words for a learner (preferring content words over function words)
4. For each selected word, the LLM provides a translation, an example sentence from the transcript, and the part of speech

## Anki Import

To import the generated CSV into Anki:

1. Open Anki
2. Go to **File > Import**
3. Select the `.csv` file
4. In the import dialog:
   - Set **Fields separated by**: Tab or Semicolon (matching your `anki.separator` config)
   - Set **Field 1** to a new field (e.g. "Word")
   - Set **Field 2** to a new field (e.g. "Translation")
   - Set **Field 3** to a new field (e.g. "Example")
   - Set **Field 4** to a new field (e.g. "POS")
   - Choose a note type and deck
5. Click **Import**

See [Anki's importing documentation](https://docs.ankiweb.net/importing/text-files.html) for more details.

## How It Works

LangWatch runs a five-step pipeline for each video:

```
[1/5] Download
      yt-dlp fetches video metadata, resolves the caption language,
      then downloads the video and captions to a temp directory.

[2/5] Process Captions
      The raw SRT file is parsed and deduplicated to remove YouTube's
      rolling caption artifacts (overlapping lines, exact duplicates,
      scrolling text patterns).

[3/5] Translate Subtitles
      Captions are sent to the LLM in batches for translation.
      If batch translation fails, falls back to translating one at a time.

[4/5] Generate Gloss
      The transcript is split into sentences, and each sentence is sent
      to the LLM for word-by-word glossing and free translation.

[5/5] Extract Vocabulary
      Word frequencies are computed, filtered, and sent to the LLM
      for curation. The results are exported as an Anki-compatible CSV.
```

### Caption Deduplication

YouTube's auto-generated captions use a "rolling" format where each subtitle entry contains two lines — the previous line scrolling up and a new line appearing below. This creates duplicates in the raw SRT. LangWatch's deduplicator handles five patterns:

1. **First subtitle** — kept as-is
2. **Exact duplicates** — merged by extending the end timestamp
3. **Rolling pattern** — previous text matches the first line of current; only the new line is kept
4. **Multiline rolling** — same pattern with multiline subtitles
5. **Normal subtitles** — passed through unchanged

After deduplication, entries are re-indexed sequentially and empty entries are removed.

## License

MIT
