import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


class VideoProcessingError(Exception):
    """A safe, user-facing video processing error."""


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    has_audio: bool


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    offset_seconds: float


@dataclass(frozen=True)
class AudioMetadata:
    duration_seconds: float
    file_size: int


class VideoService:
    def __init__(self, processed_dir: Path, chunk_minutes: int = 20, overlap_seconds: int = 2):
        self.processed_dir = processed_dir
        self.chunk_seconds = max(60, chunk_minutes * 60)
        self.overlap_seconds = max(0, overlap_seconds)

    @staticmethod
    def ensure_tools() -> None:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise VideoProcessingError("FFmpeg가 설치되어 있지 않습니다. README의 설치 안내를 확인해 주세요.")

    def probe(self, path: Path) -> VideoMetadata:
        self.ensure_tools()
        command = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=True)
            payload = json.loads(completed.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise VideoProcessingError("손상되었거나 읽을 수 없는 MP4 영상입니다.") from exc

        video_stream = next((item for item in payload.get("streams", []) if item.get("codec_type") == "video"), None)
        audio_stream = next((item for item in payload.get("streams", []) if item.get("codec_type") == "audio"), None)
        if video_stream is None:
            raise VideoProcessingError("영상 트랙을 찾을 수 없습니다.")
        try:
            duration = float(payload.get("format", {}).get("duration") or video_stream.get("duration"))
        except (TypeError, ValueError) as exc:
            raise VideoProcessingError("영상 길이를 확인할 수 없습니다.") from exc
        if duration <= 0:
            raise VideoProcessingError("영상 길이가 올바르지 않습니다.")
        return VideoMetadata(
            duration_seconds=duration,
            width=int(video_stream.get("width") or 0),
            height=int(video_stream.get("height") or 0),
            has_audio=audio_stream is not None,
        )

    def extract_audio(self, video_path: Path, project_id: str) -> Path:
        self.ensure_tools()
        project_dir = self.processed_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        output = project_dir / "audio.wav"
        command = [
            "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
        ]
        try:
            subprocess.run(command, capture_output=True, text=True, timeout=7200, check=True)
        except subprocess.CalledProcessError as exc:
            raise VideoProcessingError("영상에서 음성을 추출하지 못했습니다.") from exc
        except subprocess.TimeoutExpired as exc:
            raise VideoProcessingError("음성 추출 시간이 너무 오래 걸려 중단되었습니다.") from exc
        if not output.exists() or output.stat().st_size == 0:
            raise VideoProcessingError("추출된 오디오가 비어 있습니다.")
        return output

    def validate_extracted_audio(self, audio_path: Path, video_duration_seconds: float) -> AudioMetadata:
        if not audio_path.exists() or audio_path.stat().st_size <= 0:
            raise VideoProcessingError("추출된 오디오 파일이 없거나 비어 있습니다.")
        command = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", str(audio_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=True)
            duration = float(json.loads(completed.stdout).get("format", {}).get("duration"))
        except (subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise VideoProcessingError("추출된 오디오 길이를 확인하지 못했습니다.") from exc
        allowed_difference = max(5.0, video_duration_seconds * 0.05)
        if duration <= 0 or abs(duration - video_duration_seconds) > allowed_difference:
            raise VideoProcessingError("추출된 오디오 길이가 원본 영상과 일치하지 않습니다.")
        return AudioMetadata(duration_seconds=duration, file_size=audio_path.stat().st_size)

    def split_audio(self, audio_path: Path, duration_seconds: float) -> List[AudioChunk]:
        chunks: List[AudioChunk] = []
        start = 0.0
        index = 0
        while start < duration_seconds:
            length = min(self.chunk_seconds + self.overlap_seconds, duration_seconds - start)
            output = audio_path.parent / f"chunk-{index:03d}.mp3"
            command = [
                "ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(start),
                "-t", str(length), "-i", str(audio_path), "-ac", "1", "-ar", "16000",
                "-c:a", "libmp3lame", "-b:a", "64k", str(output),
            ]
            try:
                subprocess.run(command, capture_output=True, text=True, timeout=1800, check=True)
            except subprocess.SubprocessError as exc:
                raise VideoProcessingError("긴 오디오를 전사용 조각으로 나누지 못했습니다.") from exc
            if not output.exists() or output.stat().st_size <= 0:
                raise VideoProcessingError("전사용 오디오 조각이 비어 있습니다.")
            chunks.append(AudioChunk(output, start))
            start += self.chunk_seconds
            index += 1
        return chunks
