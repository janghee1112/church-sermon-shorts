from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from app.core.config import Settings, get_settings


class StorageError(Exception):
    """A storage failure that is safe to translate to a user-facing message."""


@dataclass(frozen=True)
class StorageObjectMetadata:
    size: int
    content_type: str
    etag: str | None = None


@dataclass(frozen=True)
class CompletedPart:
    part_number: int
    etag: str


class StorageService(Protocol):
    backend_name: str

    def create_multipart_upload(self, object_key: str, content_type: str) -> str: ...

    def generate_part_upload_url(
        self, object_key: str, upload_id: str, part_number: int, expires_in: int
    ) -> str: ...

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: Sequence[CompletedPart]
    ) -> None: ...

    def abort_multipart_upload(self, object_key: str, upload_id: str) -> None: ...

    def get_object_metadata(self, object_key: str) -> StorageObjectMetadata: ...

    def generate_download_url(
        self, object_key: str, expires_in: int, download_name: str | None = None
    ) -> str: ...

    def upload_file(self, source: Path, object_key: str, content_type: str) -> StorageObjectMetadata: ...

    def delete_object(self, object_key: str) -> None: ...

    def delete_project_objects(self, project_id: str) -> int: ...


def project_original_key(project_id: str) -> str:
    return f"projects/{project_id}/original/source.mp4"


def project_render_key(project_id: str, version: int, file_name: str) -> str:
    safe_name = Path(file_name).name
    return f"projects/{project_id}/renders/v{version}/{safe_name}"


def validate_project_object_key(project_id: str, object_key: str) -> bool:
    prefix = f"projects/{project_id}/"
    return object_key.startswith(prefix) and ".." not in object_key.split("/")


def get_storage_service(settings: Settings | None = None) -> StorageService:
    resolved = settings or get_settings()
    if not resolved.uses_r2:
        raise StorageError("현재 저장소는 R2 모드가 아닙니다.")
    from app.services.r2_storage_service import R2StorageService

    return R2StorageService(resolved)
