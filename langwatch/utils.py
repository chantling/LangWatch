from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def sanitize_filename(title: str, max_length: int = 200) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "", title)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()
    return sanitized


def build_output_path(download_dir: str, title: str, upload_date: str | None, extension: str) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    if upload_date and len(upload_date) >= 8:
        try:
            parsed = datetime.strptime(upload_date[:8], "%Y%m%d")
            date_str = parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

    safe_title = sanitize_filename(title)
    filename = f"{date_str} - {safe_title}.{extension}"
    return Path(download_dir) / filename


def ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def change_extension(path: Path, new_extension: str) -> Path:
    return path.with_suffix(f".{new_extension}")


def translated_path(path: Path, extension: str) -> Path:
    return path.with_name(f"{path.stem}-translated.{extension}")
