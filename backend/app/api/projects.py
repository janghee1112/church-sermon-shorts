import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterator, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.database.session import get_db
from app.models import CandidateTitle, ClipCandidate, Project, TranscriptSegment
from app.schemas.api import CandidatesResponse, ProjectResponse, TranscriptResponse
from app.services.project_cleanup_service import ProjectCleanupError, cleanup_project
from app.services.project_service import analyze_project, project_to_dict
from app.services.video_service import VideoProcessingError, VideoService
from app.services.storage_service import StorageError, get_storage_service


router = APIRouter(prefix="/api/projects", tags=["projects"])
settings = get_settings()
IN_PROGRESS = {"extracting_audio", "transcribing", "analyzing"}


def get_project_or_404(project_id: str, db: Session) -> Project:
    try:
        UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.") from exc
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if settings.uses_r2:
        await file.close()
        raise HTTPException(status_code=409, detail="대용량 영상은 R2 직접 업로드를 사용해 주세요.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드할 파일을 선택해 주세요.")
    extension = Path(file.filename).suffix.lower()
    if extension != ".mp4" or file.content_type != "video/mp4":
        raise HTTPException(status_code=415, detail="MP4 형식의 영상만 업로드할 수 있습니다.")

    project_id = str(uuid4())
    stored_path = settings.upload_dir / f"{project_id}.mp4"
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    total = 0
    try:
        with stored_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"파일 크기는 {settings.max_upload_size_mb}MB 이하여야 합니다.")
                destination.write(chunk)
    except Exception:
        if stored_path.exists():
            stored_path.unlink()
        raise
    finally:
        await file.close()

    if total == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다.")

    video_service = VideoService(settings.processed_dir)
    try:
        metadata = video_service.probe(stored_path)
        if not metadata.has_audio:
            raise VideoProcessingError("오디오 트랙이 없는 영상은 분석할 수 없습니다.")
        if metadata.duration_seconds > settings.max_video_duration_minutes * 60:
            raise VideoProcessingError(f"영상 길이는 {settings.max_video_duration_minutes}분 이하여야 합니다.")
    except VideoProcessingError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    project = Project(
        id=project_id,
        original_file_name=Path(file.filename).name,
        stored_file_path=str(stored_path.resolve()),
        duration_seconds=metadata.duration_seconds,
        width=metadata.width,
        height=metadata.height,
        file_size=total,
        status="uploaded",
        progress=10,
        analysis_mode="mock" if settings.use_mock_ai else "real",
        transcription_model="mock-transcription" if settings.use_mock_ai else settings.openai_transcribe_model,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_dict(project)


@router.post("/{project_id}/analyze", response_model=ProjectResponse, status_code=status.HTTP_202_ACCEPTED)
def start_analysis(project_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    project = get_project_or_404(project_id, db)
    if project.status in IN_PROGRESS:
        return project_to_dict(project)
    if project.status == "completed":
        return project_to_dict(project)
    if project.status == "uploading":
        raise HTTPException(status_code=409, detail="영상 업로드 확인이 아직 완료되지 않았습니다.")
    project.status = "extracting_audio"
    project.progress = 10
    project.error_message = None
    project.error_stage = None
    db.commit()
    background_tasks.add_task(analyze_project, project.id)
    return project_to_dict(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    return project_to_dict(get_project_or_404(project_id, db))


@router.get("/{project_id}/transcript", response_model=TranscriptResponse)
def get_transcript(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = get_project_or_404(project_id, db)
    segments = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.project_id == project.id)
        .options(selectinload(TranscriptSegment.words))
        .order_by(TranscriptSegment.segment_order)
    ).all()
    if project.status != "completed" and not segments:
        raise HTTPException(status_code=409, detail="대본이 아직 준비되지 않았습니다.")
    return {"project_id": project.id, "full_text": " ".join(item.text for item in segments), "segments": segments}


@router.get("/{project_id}/candidates", response_model=CandidatesResponse)
def get_candidates(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = get_project_or_404(project_id, db)
    candidates = db.scalars(
        select(ClipCandidate)
        .where(ClipCandidate.project_id == project.id)
        .options(selectinload(ClipCandidate.titles))
        .order_by(ClipCandidate.candidate_order)
    ).all()
    if project.status != "completed":
        raise HTTPException(status_code=409, detail="후보 분석이 아직 완료되지 않았습니다.")
    return {
        "project_id": project.id,
        "analysis_mode": project.analysis_mode,
        "sermon_summary": project.sermon_summary or "",
        "sermon_topics": json.loads(project.sermon_topics or "[]"),
        "candidates": [
            {
                "id": item.id,
                "candidate_order": item.candidate_order,
                "recommendation_type": item.recommendation_type,
                "start_sec": item.start_sec,
                "end_sec": item.end_sec,
                "duration_sec": item.duration_sec,
                "transcript": item.transcript,
                "main_topic": item.main_topic,
                "selection_reason": item.selection_reason,
                "scores": {
                    "centrality": item.centrality_score,
                    "standalone": item.standalone_score,
                    "hook": item.hook_score,
                    "emotional_impact": item.emotional_score,
                    "overall": item.overall_score,
                },
                **_candidate_metadata(item),
                "titles": sorted(item.titles, key=lambda title: title.title_order),
            }
            for item in candidates
        ],
        "debug": _build_debug_payload(project, candidates, db) if settings.is_development else None,
    }


def _build_debug_payload(project: Project, candidates: list[ClipCandidate], db: Session) -> dict:
    first = db.scalar(
        select(TranscriptSegment)
        .where(TranscriptSegment.project_id == project.id)
        .order_by(TranscriptSegment.segment_order)
        .limit(1)
    )
    last = db.scalar(
        select(TranscriptSegment)
        .where(TranscriptSegment.project_id == project.id)
        .order_by(TranscriptSegment.segment_order.desc())
        .limit(1)
    )

    def segment_payload(segment: Optional[TranscriptSegment]) -> Optional[dict]:
        if segment is None:
            return None
        return {
            "segment_id": segment.id,
            "start_sec": segment.start_sec,
            "end_sec": segment.end_sec,
            "text": segment.text,
        }

    return {
        "analysis_mode": project.analysis_mode,
        "transcription_model": project.transcription_model,
        "transcript_segment_count": project.transcript_segment_count,
        "transcript_char_count": project.transcript_char_count,
        "first_segment": segment_payload(first),
        "last_segment": segment_payload(last),
        "candidates": [
            {
                "candidate_order": item.candidate_order,
                "start_segment_id": item.start_segment_id,
                "end_segment_id": item.end_segment_id,
                "segment_count": item.segment_count,
                **_candidate_metadata(item),
            }
            for item in candidates
        ],
    }


def _candidate_metadata(candidate: ClipCandidate) -> dict:
    try:
        metadata = json.loads(candidate.analysis_metadata or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    context_integrity = metadata.get("context_integrity", True)
    if isinstance(context_integrity, str):
        context_integrity = context_integrity.strip().lower() not in {"false", "fail", "0", "no"}
    return {
        "shorts_score": int(metadata.get("shorts_score", candidate.overall_score or 0)),
        "opening_3s_score": int(metadata.get("opening_3s_score", candidate.hook_score or 0)),
        "scroll_stop_score": int(metadata.get("scroll_stop_score", candidate.hook_score or 0)),
        "non_christian_clarity_score": int(metadata.get("non_christian_clarity_score", candidate.standalone_score or 0)),
        "emotional_triggers": [str(value) for value in metadata.get("emotional_triggers", [])],
        "context_integrity": bool(context_integrity),
        "hook_strength": int(metadata.get("hook_strength", candidate.hook_score or 0)),
        "universal_relevance": int(metadata.get("universal_relevance", candidate.centrality_score or 0)),
        "curiosity_gap": int(metadata.get("curiosity_gap", candidate.hook_score or 0)),
        "payoff_strength": int(metadata.get("payoff_strength", candidate.standalone_score or 0)),
        "standalone_clarity": int(metadata.get("standalone_clarity", candidate.standalone_score or 0)),
        "emotional_intensity": int(metadata.get("emotional_intensity", candidate.emotional_score or 0)),
        "brevity_efficiency": int(metadata.get("brevity_efficiency", 0)),
        "title_potential_score": int(metadata.get("title_potential_score", candidate.hook_score or 0)),
        "information_density_score": int(metadata.get("information_density_score", 0)),
        "core_theme": metadata.get("core_theme") or candidate.main_topic,
    }


def _file_iterator(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as source:
        source.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = source.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


@router.get("/{project_id}/video")
def stream_video(project_id: str, range_header: Optional[str] = Header(None, alias="Range"), db: Session = Depends(get_db)) -> Response:
    project = get_project_or_404(project_id, db)
    if settings.uses_r2 and project.original_object_key:
        try:
            url = get_storage_service(settings).generate_download_url(
                project.original_object_key, settings.r2_read_url_expiry_seconds
            )
        except StorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Cache-Control": "private, no-store"})
    path = Path(project.stored_file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="원본 영상 파일을 찾을 수 없습니다.")
    file_size = path.stat().st_size
    headers = {"Accept-Ranges": "bytes", "Content-Disposition": "inline"}
    if not range_header:
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(_file_iterator(path, 0, file_size - 1), media_type="video/mp4", headers=headers)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not match:
        raise HTTPException(status_code=416, detail="올바르지 않은 Range 요청입니다.")
    start = int(match.group(1) or 0)
    end = int(match.group(2) or min(file_size - 1, start + 4 * 1024 * 1024 - 1))
    if start >= file_size or end < start:
        raise HTTPException(status_code=416, detail="요청 범위가 영상 크기를 벗어났습니다.")
    end = min(end, file_size - 1)
    headers.update({
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(end - start + 1),
    })
    return StreamingResponse(_file_iterator(path, start, end), status_code=206, media_type="video/mp4", headers=headers)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)) -> Response:
    project = get_project_or_404(project_id, db)
    try:
        cleanup_project(db, project)
    except ProjectCleanupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
