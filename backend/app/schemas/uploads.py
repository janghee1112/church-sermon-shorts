from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.api import ProjectResponse


class UploadConfigResponse(BaseModel):
    storage_backend: Literal["local", "r2"]
    multipart_enabled: bool
    part_size: Optional[int] = None


class MultipartInitRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=500)
    file_size: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=120)

    @field_validator("file_name")
    @classmethod
    def safe_file_name(cls, value: str) -> str:
        if value != value.replace("\\", "/").split("/")[-1]:
            raise ValueError("파일 이름이 올바르지 않습니다.")
        return value


class UploadPartResponse(BaseModel):
    part_number: int
    upload_url: str


class MultipartInitResponse(BaseModel):
    session_id: str
    project_id: str
    upload_id: str
    object_key: str
    part_size: int
    total_parts: int
    parts: list[UploadPartResponse]


class CompletedUploadPart(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=500)


class MultipartCompleteRequest(BaseModel):
    session_id: str
    parts: list[CompletedUploadPart] = Field(min_length=1, max_length=10_000)


class MultipartCompleteResponse(ProjectResponse):
    pass


class MultipartAbortRequest(BaseModel):
    session_id: str
