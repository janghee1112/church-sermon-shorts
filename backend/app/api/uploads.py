from __future__ import annotations

import math
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models import MultipartUploadSession, Project
from app.schemas.uploads import (
    MultipartAbortRequest,
    MultipartCompleteRequest,
    MultipartCompleteResponse,
    MultipartInitRequest,
    MultipartInitResponse,
    UploadConfigResponse,
)
from app.services.project_service import project_to_dict
from app.services.storage_service import (
    CompletedPart,
    StorageError,
    get_storage_service,
    project_original_key,
    validate_project_object_key,
)
from app.services.video_service import VideoProcessingError, VideoService


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _storage_error(exc: StorageError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


def _session_or_404(db: Session, session_id: str) -> MultipartUploadSession:
    try:
        UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="업로드 세션을 찾을 수 없습니다.") from exc
    session = db.get(MultipartUploadSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="업로드 세션을 찾을 수 없습니다.")
    if not validate_project_object_key(session.project_id, session.object_key):
        raise HTTPException(status_code=409, detail="업로드 파일 경로를 안전하게 확인하지 못했습니다.")
    return session


@router.get("/config", response_model=UploadConfigResponse)
def upload_config() -> dict:
    settings = get_settings()
    return {
        "storage_backend": settings.storage_backend,
        "multipart_enabled": settings.uses_r2,
        "part_size": settings.r2_multipart_part_size_mb * 1024 * 1024 if settings.uses_r2 else None,
    }


@router.post("/multipart/init", response_model=MultipartInitResponse, status_code=status.HTTP_201_CREATED)
def initiate_multipart(payload: MultipartInitRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.uses_r2:
        raise HTTPException(status_code=409, detail="현재 서버는 직접 R2 업로드 모드가 아닙니다.")
    if Path(payload.file_name).suffix.lower() != ".mp4" or payload.content_type != "video/mp4":
        raise HTTPException(status_code=415, detail="MP4 형식의 영상만 업로드할 수 있습니다.")
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if payload.file_size > max_bytes:
        raise HTTPException(status_code=413, detail=f"파일 크기는 {settings.max_upload_size_mb}MB 이하여야 합니다.")

    project_id = str(uuid4())
    session_id = str(uuid4())
    object_key = project_original_key(project_id)
    part_size = settings.r2_multipart_part_size_mb * 1024 * 1024
    total_parts = math.ceil(payload.file_size / part_size)
    if total_parts > 10_000:
        raise HTTPException(status_code=413, detail="업로드 파일이 multipart 제한을 초과합니다.")
    try:
        storage = get_storage_service(settings)
        provider_upload_id = storage.create_multipart_upload(object_key, payload.content_type)
        urls = [
            {
                "part_number": part_number,
                "upload_url": storage.generate_part_upload_url(
                    object_key,
                    provider_upload_id,
                    part_number,
                    settings.r2_upload_url_expiry_seconds,
                ),
            }
            for part_number in range(1, total_parts + 1)
        ]
    except StorageError as exc:
        raise _storage_error(exc) from exc

    project = Project(
        id=project_id,
        original_file_name=Path(payload.file_name).name,
        stored_file_path="",
        original_object_key=object_key,
        original_content_type=payload.content_type,
        duration_seconds=0,
        width=0,
        height=0,
        file_size=payload.file_size,
        status="uploading",
        progress=0,
        analysis_mode="mock" if settings.use_mock_ai else "real",
        transcription_model="mock-transcription" if settings.use_mock_ai else settings.openai_transcribe_model,
    )
    session = MultipartUploadSession(
        id=session_id,
        project_id=project_id,
        provider_upload_id=provider_upload_id,
        object_key=object_key,
        expected_file_size=payload.file_size,
        content_type=payload.content_type,
        part_size=part_size,
        status="uploading",
    )
    db.add_all([project, session])
    db.commit()
    return {
        "session_id": session_id,
        "project_id": project_id,
        "upload_id": provider_upload_id,
        "object_key": object_key,
        "part_size": part_size,
        "total_parts": total_parts,
        "parts": urls,
    }


@router.post("/multipart/complete", response_model=MultipartCompleteResponse)
def complete_multipart(payload: MultipartCompleteRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    session = _session_or_404(db, payload.session_id)
    project = db.get(Project, session.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    if session.status == "completed" and project.status == "uploaded":
        return project_to_dict(project)
    if session.status != "uploading":
        raise HTTPException(status_code=409, detail="이미 종료된 업로드 세션입니다.")
    part_numbers = [part.part_number for part in payload.parts]
    expected_parts = math.ceil(session.expected_file_size / session.part_size)
    if sorted(part_numbers) != list(range(1, expected_parts + 1)) or len(set(part_numbers)) != len(part_numbers):
        raise HTTPException(status_code=422, detail="업로드 조각 정보가 올바르지 않습니다.")

    try:
        storage = get_storage_service(settings)
        storage.complete_multipart_upload(
            session.object_key,
            session.provider_upload_id,
            [CompletedPart(item.part_number, item.etag) for item in payload.parts],
        )
        session.status = "verifying"
        db.commit()
        metadata = storage.get_object_metadata(session.object_key)
        if metadata.size != session.expected_file_size:
            storage.delete_object(session.object_key)
            db.delete(project)
            db.commit()
            raise HTTPException(status_code=422, detail="업로드된 영상 크기가 원본과 일치하지 않습니다.")
        if metadata.content_type.split(";", 1)[0].strip().lower() != "video/mp4":
            storage.delete_object(session.object_key)
            db.delete(project)
            db.commit()
            raise HTTPException(status_code=422, detail="업로드된 파일의 형식이 MP4가 아닙니다.")
        read_url = storage.generate_download_url(
            session.object_key, settings.r2_read_url_expiry_seconds
        )
        video_metadata = VideoService(settings.processed_dir).probe(read_url)
    except StorageError as exc:
        raise _storage_error(exc) from exc
    except VideoProcessingError as exc:
        try:
            get_storage_service(settings).delete_object(session.object_key)
        except StorageError:
            pass
        db.delete(project)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not video_metadata.has_audio:
        storage.delete_object(session.object_key)
        db.delete(project)
        db.commit()
        raise HTTPException(status_code=422, detail="오디오 트랙이 없는 영상은 분석할 수 없습니다.")
    if video_metadata.duration_seconds > settings.max_video_duration_minutes * 60:
        storage.delete_object(session.object_key)
        db.delete(project)
        db.commit()
        raise HTTPException(status_code=422, detail=f"영상 길이는 {settings.max_video_duration_minutes}분 이하여야 합니다.")

    project.duration_seconds = video_metadata.duration_seconds
    project.width = video_metadata.width
    project.height = video_metadata.height
    project.file_size = session.expected_file_size
    project.status = "uploaded"
    project.progress = 10
    session.status = "completed"
    db.commit()
    return project_to_dict(project)


@router.post("/multipart/abort", status_code=status.HTTP_204_NO_CONTENT)
def abort_multipart(payload: MultipartAbortRequest, db: Session = Depends(get_db)) -> Response:
    session = _session_or_404(db, payload.session_id)
    if session.status == "uploading":
        try:
            get_storage_service().abort_multipart_upload(
                session.object_key, session.provider_upload_id
            )
        except StorageError as exc:
            raise _storage_error(exc) from exc
    elif session.status == "verifying":
        try:
            get_storage_service().delete_object(session.object_key)
        except StorageError as exc:
            raise _storage_error(exc) from exc
    project = db.get(Project, session.project_id)
    if project is not None:
        db.delete(project)
    else:
        db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
