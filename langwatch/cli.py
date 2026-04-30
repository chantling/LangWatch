from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

from langwatch.config import AppConfig, load_config
from langwatch.caption_processor import process_captions, parse_transcript
from langwatch.downloader import download
from langwatch.gloss_generator import generate_and_save_gloss
from langwatch.subtitle_generator import translate_and_save_srt, save_original_srt
from langwatch.translator import LLMTranslator
from langwatch.utils import change_extension, translated_path
from langwatch.vocabulary import generate_vocabulary

console = Console(stderr=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="langwatch",
        description="Language learning video downloader with bilingual subtitles, gloss, and Anki export.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="URL of the video to download (YouTube and other yt-dlp supported sites)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        help="Override video resolution (e.g. 1080, 720, 480)",
    )
    parser.add_argument(
        "--source-language",
        help="Force caption language code (e.g. 'de', 'es', 'fr')",
    )
    parser.add_argument(
        "--target-language",
        help="Override target/translation language",
    )
    parser.add_argument(
        "--llm",
        help="Name of LLM API to use from config (e.g. 'ollama-local', 'zai-glm')",
    )
    parser.add_argument(
        "--no-anki",
        action="store_true",
        help="Skip Anki CSV export",
    )
    parser.add_argument(
        "--no-gloss",
        action="store_true",
        help="Skip gloss generation",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip bilingual subtitle generation",
    )
    return parser.parse_args(argv)


def _resolve_api(config: AppConfig, llm_name: str | None) -> None:
    if llm_name:
        if llm_name not in config.llm.apis:
            available = ", ".join(config.llm.apis.keys())
            raise ValueError(
                f"LLM API '{llm_name}' not found in config. Available: {available}"
            )
        config.llm.active = llm_name


def process_url(url: str, config: AppConfig, args: argparse.Namespace) -> None:
    console.print(f"\n[bold cyan]Processing:[/bold cyan] {url}")

    api_config = config.llm.get_active_api()
    console.print(
        f"[dim]Using LLM: {config.llm.active} ({api_config.model} @ {api_config.api_base})[/dim]\n"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        task_dl = progress.add_task("[1/5] Downloading video and captions...", total=None)
        result = download(
            url=url,
            config=config,
            resolution_override=args.resolution,
            cli_source_lang=args.source_language,
        )
        progress.update(task_dl, completed=1, total=1)

        task_cap = progress.add_task("[2/5] Processing captions...", total=None)
        subtitles = process_captions(result.srt_path)
        transcript = parse_transcript(subtitles)
        progress.update(task_cap, completed=1, total=1)

        original_srt_path = change_extension(result.video_path, "srt")
        save_original_srt(subtitles, original_srt_path)

        source_lang = result.source_language
        target_lang = args.target_language or config.target_language

        translator = LLMTranslator(api_config)

        if not args.no_subtitles:
            bilingual_srt_path = translated_path(result.video_path, "srt")
            task_sub = progress.add_task(
                "[3/5] Translating subtitles...",
                total=max(1, len(subtitles) // max(len(subtitles), 1)),
            )
            translate_and_save_srt(subtitles, translator, target_lang, source_lang, bilingual_srt_path)
            progress.update(task_sub, completed=True)

        if not args.no_gloss:
            gloss_path = change_extension(result.video_path, "txt")
            task_gloss = progress.add_task(
                "[4/5] Generating gloss...",
                total=None,
            )
            generate_and_save_gloss(subtitles, translator, target_lang, source_lang, gloss_path)
            progress.update(task_gloss, completed=1, total=1)

        if not args.no_anki:
            csv_path = change_extension(result.video_path, "csv")
            task_vocab = progress.add_task("[5/5] Extracting vocabulary...", total=None)
            generate_vocabulary(transcript, translator, config.anki, source_lang, target_lang, csv_path)
            progress.update(task_vocab, completed=1, total=1)

    console.print("\n[bold green]Done![/bold green] Files created:")
    console.print(f"  Video:              {result.video_path}")
    console.print(f"  Subtitles (orig):   {change_extension(result.video_path, 'srt')}")
    if not args.no_subtitles:
        console.print(f"  Subtitles (bilingual): {translated_path(result.video_path, 'srt')}")
    if not args.no_gloss:
        console.print(f"  Gloss:              {change_extension(result.video_path, 'txt')}")
    if not args.no_anki:
        console.print(f"  Vocabulary:         {change_extension(result.video_path, 'csv')}")
    console.print()


def interactive_loop(config: AppConfig, args: argparse.Namespace) -> None:
    console.print("[bold]LangWatch[/bold] - Language Learning Video Downloader")
    api_config = config.llm.get_active_api()
    console.print(
        f"[dim]LLM: {config.llm.active} ({api_config.model}) | "
        f"Type a video URL to download, or 'exit'/'quit' to quit.[/dim]\n"
    )

    while True:
        try:
            url = input("Enter video URL (or 'exit' to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if not url:
            continue

        if url.lower() in ("exit", "quit", "q"):
            console.print("Goodbye!")
            break

        try:
            process_url(url, config, args)
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)

    if args.no_anki:
        config.anki.enabled = False

    _resolve_api(config, args.llm)

    if args.url:
        try:
            process_url(args.url, config, args)
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}")
            sys.exit(1)
    else:
        interactive_loop(config, args)


if __name__ == "__main__":
    main()
