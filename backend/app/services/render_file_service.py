import re
from pathlib import Path
from typing import Iterator, Optional, Tuple


def ensure_managed_file(path_value: str, processed_dir: Path) -> Path:
    path = Path(path_value).resolve()
    root = processed_dir.resolve()
    if path == root or root not in path.parents:
        raise ValueError("완성 영상 경로가 올바르지 않습니다.")
    return path


def parse_range_header(value: Optional[str], file_size: int) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if match is None:
        raise ValueError("올바르지 않은 Range 요청입니다.")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise ValueError("올바르지 않은 Range 요청입니다.")
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        suffix = int(end_text)
        start = max(0, file_size - suffix)
        end = file_size - 1
    if start < 0 or start >= file_size or end < start:
        raise ValueError("요청한 영상 범위를 제공할 수 없습니다.")
    return start, min(end, file_size - 1)


def iter_file(path: Path, start: int = 0, end: Optional[int] = None, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    remaining = None if end is None else end - start + 1
    with path.open("rb") as file_handle:
        file_handle.seek(start)
        while remaining is None or remaining > 0:
            data = file_handle.read(chunk_size if remaining is None else min(chunk_size, remaining))
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data


def safe_download_name(title: str, version: int) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "", title).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)[:60] or "설교쇼츠"
    return f"설교쇼츠_{cleaned}_v{version}.mp4"

