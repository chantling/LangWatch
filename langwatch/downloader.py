from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from yt_dlp import YoutubeDL

from langwatch.config import AppConfig
from langwatch.utils import build_output_path, ensure_directory, change_extension


@dataclass
class AvailableCaption:
    lang_code: str
    lang_name: str
    is_manual: bool


@dataclass
class DownloadResult:
    video_path: Path
    srt_path: Path
    metadata: dict[str, Any]
    source_language: str


def _get_available_captions(info: dict) -> list[AvailableCaption]:
    captions: list[AvailableCaption] = []

    manual_subs = info.get("subtitles") or {}
    for lang_code, tracks in manual_subs.items():
        lang_name = lang_code
        if tracks:
            for track in tracks:
                lang_name = track.get("name", lang_code)
                break
        captions.append(AvailableCaption(
            lang_code=lang_code,
            lang_name=lang_name,
            is_manual=True,
        ))

    auto_subs = info.get("automatic_captions") or {}
    for lang_code, tracks in auto_subs.items():
        if any(c.lang_code == lang_code and c.is_manual for c in captions):
            continue
        lang_name = lang_code
        if tracks:
            for track in tracks:
                lang_name = track.get("name", lang_code)
                break
        captions.append(AvailableCaption(
            lang_code=lang_code,
            lang_name=lang_name,
            is_manual=False,
        ))

    return captions


def _detect_video_language(info: dict) -> str | None:
    return info.get("language") or None


def resolve_caption_language(
    info: dict,
    config_source_lang: str,
    cli_source_lang: str | None,
    available_captions: list[AvailableCaption],
) -> str:
    def _prompt_language() -> str:
        if not available_captions:
            raise ValueError("No captions available for this video.")

        manual = [c for c in available_captions if c.is_manual]
        auto = [c for c in available_captions if not c.is_manual]

        print("\nAvailable captions:")
        idx = 1
        mapping: dict[int, str] = {}
        if manual:
            print("  Manual:")
            for c in manual:
                print(f"    [{idx}] {c.lang_code} ({c.lang_name})")
                mapping[idx] = c.lang_code
                idx += 1
        if auto:
            print("  Auto-generated:")
            for c in auto:
                print(f"    [{idx}] {c.lang_code} ({c.lang_name})")
                mapping[idx] = c.lang_code
                idx += 1

        while True:
            try:
                choice = int(input(f"Select caption language [1-{idx - 1}]: "))
                if choice in mapping:
                    return mapping[choice]
                print(f"Please enter a number between 1 and {idx - 1}.")
            except (ValueError, EOFError):
                print("Invalid input. Please enter a number.")
                if not available_captions:
                    raise

    available_codes = {c.lang_code for c in available_captions}

    if cli_source_lang:
        if cli_source_lang in available_codes:
            return cli_source_lang
        print(f"\nRequested language '{cli_source_lang}' is not available for this video.")
        return _prompt_language()

    if config_source_lang and config_source_lang != "auto":
        if config_source_lang in available_codes:
            detected = _detect_video_language(info)
            if detected and detected != config_source_lang:
                print(
                    f"\nWarning: Config specifies '{config_source_lang}' but video metadata indicates '{detected}'."
                )
                return _prompt_language()
            return config_source_lang
        print(f"\nConfig language '{config_source_lang}' is not available for this video.")
        return _prompt_language()

    detected = _detect_video_language(info)
    if detected and detected in available_codes:
        return detected

    return _prompt_language()


def _get_format_selector(resolution: int) -> str:
    return f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]/best"


def download(
    url: str,
    config: AppConfig,
    resolution_override: int | None = None,
    cli_source_lang: str | None = None,
    progress_hooks: list | None = None,
) -> DownloadResult:
    resolution = resolution_override or config.video_resolution
    tmpdir_obj = TemporaryDirectory()
    tmpdir = Path(tmpdir_obj.name)

    try:
        info_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
        }
        with YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "Untitled")
        upload_date = info.get("upload_date", "")
        video_id = info.get("id", "")

        available_captions = _get_available_captions(info)
        source_lang = resolve_caption_language(
            info, config.source_language, cli_source_lang, available_captions
        )

        has_manual = any(
            c.lang_code == source_lang and c.is_manual for c in available_captions
        )

        video_path = build_output_path(config.download_dir, title, upload_date, "mp4")
        srt_path = change_extension(video_path, "srt")
        ensure_directory(video_path)

        download_opts: dict[str, Any] = {
            "format": _get_format_selector(resolution),
            "outtmpl": {
                "default": str(tmpdir / "video.%(ext)s"),
            },
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                },
                {
                    "key": "FFmpegSubtitlesConvertor",
                    "format": "srt",
                    "when": "before_dl",
                },
            ],
            "subtitleslangs": [source_lang],
            "writesubtitles": has_manual,
            "writeautomaticsub": not has_manual,
            "quiet": True,
            "no_warnings": True,
            "retries": 10,
            "noprogress": False,
        }

        if progress_hooks:
            download_opts["progress_hooks"] = progress_hooks

        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            download_opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

        with YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        video_files = list(tmpdir.glob("video.*"))
        video_file = None
        for vf in video_files:
            if vf.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi"):
                video_file = vf
                break
        if video_file is None and video_files:
            video_file = video_files[0]

        if video_file and video_file.exists():
            shutil.move(str(video_file), str(video_path))

        srt_files = list(tmpdir.glob("*.srt"))
        if srt_files:
            shutil.copy2(str(srt_files[0]), str(srt_path))

        metadata = {
            "video_id": video_id,
            "title": title,
            "channel": info.get("uploader", ""),
            "upload_date": upload_date,
            "duration": info.get("duration"),
            "description": info.get("description", ""),
        }

        return DownloadResult(
            video_path=video_path,
            srt_path=srt_path,
            metadata=metadata,
            source_language=source_lang,
        )
    finally:
        tmpdir_obj.cleanup()
