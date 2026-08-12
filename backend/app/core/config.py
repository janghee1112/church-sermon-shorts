from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated, List, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_transcribe_model: str = "whisper-1"
    openai_analysis_model: str = "gpt-4.1-mini"
    use_mock_ai: bool = True
    app_env: str = "development"
    max_upload_size_mb: int = 2048
    max_video_duration_minutes: int = 90
    data_dir: Path = PROJECT_ROOT
    upload_dir: Optional[Path] = None
    processed_dir: Optional[Path] = None
    database_url: str = ""
    cors_origins: Annotated[List[str], NoDecode] = ["http://localhost:3000"]
    frontend_proxy_url: str = ""
    audio_chunk_minutes: int = 20
    audio_chunk_overlap_seconds: int = 2
    render_width: int = 1080
    render_height: int = 1920
    render_fps: int = 30
    render_crf: int = 20
    render_preset: str = "medium"
    title_font_path: Path = PROJECT_ROOT / "backend" / "assets" / "fonts" / "Pretendard-Black.otf"
    subtitle_font_path: Path = PROJECT_ROOT / "backend" / "assets" / "fonts" / "NanumGothic-Bold.ttf"
    title_font_name: str = "Pretendard Black"
    subtitle_font_name: str = "NanumGothic"
    storage_backend: str = "local"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "sermon-shorts"
    r2_endpoint_url: str = ""
    r2_region: str = "auto"
    r2_multipart_part_size_mb: int = 25
    r2_upload_url_expiry_seconds: int = 14_400
    r2_read_url_expiry_seconds: int = 14_400

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "dev", "local"}

    @property
    def uses_r2(self) -> bool:
        return self.storage_backend.lower() == "r2"

    @property
    def resolved_r2_endpoint_url(self) -> str:
        if self.r2_endpoint_url.strip():
            return self.r2_endpoint_url.rstrip("/")
        if self.r2_account_id.strip():
            return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        return ""

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"local", "r2"}:
            raise ValueError("STORAGE_BACKEND는 local 또는 r2여야 합니다.")
        return normalized

    @field_validator("r2_multipart_part_size_mb")
    @classmethod
    def validate_part_size(cls, value: int) -> int:
        if not 5 <= value <= 512:
            raise ValueError("R2 multipart part size는 5~512MB여야 합니다.")
        return value

    @field_validator("title_font_path", "subtitle_font_path", mode="before")
    @classmethod
    def make_path_absolute(cls, value: object) -> Path:
        path = Path(str(value))
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @model_validator(mode="after")
    def resolve_storage(self) -> "Settings":
        # sermon_letterbox_v1 uses the bundled Nanum Gothic font for subtitles.
        # Keep stale deployment/local SUBTITLE_FONT_* overrides from bringing
        # the old Myeongjo font back into previews or rendered MP4 files.
        self.subtitle_font_path = PROJECT_ROOT / "backend" / "assets" / "fonts" / "NanumGothic-Bold.ttf"
        self.subtitle_font_name = "NanumGothic"
        data_dir = self.data_dir if self.data_dir.is_absolute() else (PROJECT_ROOT / self.data_dir).resolve()
        self.data_dir = data_dir
        self.upload_dir = self._storage_path(self.upload_dir, data_dir / "uploads")
        self.processed_dir = self._storage_path(self.processed_dir, data_dir / "processed")
        if not self.database_url:
            self.database_url = f"sqlite:///{data_dir / 'sermon_shorts.db'}"
        return self

    @staticmethod
    def _storage_path(value: Optional[Path], fallback: Path) -> Path:
        if value is None:
            return fallback.resolve()
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    assert settings.upload_dir is not None
    assert settings.processed_dir is not None
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    return settings
