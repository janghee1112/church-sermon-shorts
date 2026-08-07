from pathlib import Path
from typing import Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models import RenderJob
from app.schemas.renders import RenderResponse
from app.services.render_file_service import ensure_managed_file, iter_file, parse_range_header
from app.services.render_service import (
    RenderError,
    create_render_job,
    download_name_for_job,
    get_render,
    list_renders,
    run_render_job,
    serialize_render,
)


router = APIRouter(tags=["renders"])


def _http_error(exc: RenderError) -> HTTPException:
    status_code = 404 if exc.code in {"draft_not_found", "render_not_found"} else 422
    return HTTPException(status_code=status_code, detail=str(exc))


@router.post("/api/drafts/{draft_id}/renders", response_model=RenderResponse, status_code=status.HTTP_202_ACCEPTED)
def start_render(
    draft_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    try:
        job, created = create_render_job(db, draft_id)
        if created:
            background_tasks.add_task(run_render_job, job.id)
        return serialize_render(job)
    except RenderError as exc:
        raise _http_error(exc) from exc


@router.get("/api/renders/{render_id}", response_model=RenderResponse)
def read_render(render_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return serialize_render(get_render(db, render_id))
    except RenderError as exc:
        raise _http_error(exc) from exc


@router.get("/api/drafts/{draft_id}/renders", response_model=list[RenderResponse])
def read_draft_renders(
    draft_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> list[dict]:
    try:
        return [serialize_render(item) for item in list_renders(db, draft_id, limit)]
    except RenderError as exc:
        raise _http_error(exc) from exc


def _completed_file(render_id: int, db: Session) -> Tuple[RenderJob, Path]:
    job = get_render(db, render_id)
    if job.status != "completed" or not job.output_file_path:
        raise HTTPException(status_code=409, detail="아직 완성되지 않은 영상입니다.")
    try:
        path = ensure_managed_file(job.output_file_path, get_settings().processed_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="완성 영상 파일을 찾을 수 없습니다.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="완성 영상 파일을 찾을 수 없습니다.")
    return job, path


@router.get("/api/renders/{render_id}/video")
def stream_render_video(
    render_id: int,
    range_header: Optional[str] = Header(default=None, alias="Range"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        _, path = _completed_file(render_id, db)
    except RenderError as exc:
        raise _http_error(exc) from exc
    file_size = path.stat().st_size
    try:
        byte_range = parse_range_header(range_header, file_size)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=str(exc),
            headers={"Content-Range": f"bytes */{file_size}"},
        ) from exc
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    if byte_range is None:
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(iter_file(path), media_type="video/mp4", headers=headers)
    start, end = byte_range
    headers.update({
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(end - start + 1),
    })
    return StreamingResponse(
        iter_file(path, start, end), status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="video/mp4", headers=headers,
    )


@router.get("/api/renders/{render_id}/download")
def download_render(render_id: int, db: Session = Depends(get_db)) -> FileResponse:
    try:
        job, path = _completed_file(render_id, db)
    except RenderError as exc:
        raise _http_error(exc) from exc
    return FileResponse(
        path, media_type="video/mp4", filename=download_name_for_job(job),
        headers={"Cache-Control": "private, no-store"},
    )
