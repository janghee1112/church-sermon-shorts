from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import DraftSubtitle
from app.schemas.drafts import (
    DraftCreateRequest,
    DraftPatchRequest,
    DraftRangeRequest,
    DraftResponse,
    SubtitleMergeRequest,
    SubtitlePatchRequest,
    SubtitlePutRequest,
    SubtitleSplitRequest,
)
from app.services.draft_service import (
    DraftError,
    create_or_get_draft,
    get_draft,
    merge_subtitles,
    regenerate_subtitles,
    save_subtitles,
    serialize_draft,
    split_subtitle,
    update_draft_range,
    validate_subtitle_sequence,
)
from app.services.title_highlight import dump_highlight_ranges, legacy_highlight_range


router = APIRouter(tags=["drafts"])


def _bad_request(exc: Exception) -> HTTPException:
    message = str(exc)
    code = 404 if "찾을 수 없" in message or "존재하지 않" in message else 422
    return HTTPException(status_code=code, detail=message)


@router.post(
    "/api/projects/{project_id}/drafts",
    response_model=DraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(project_id: str, payload: DraftCreateRequest, db: Session = Depends(get_db)) -> dict:
    try:
        draft = create_or_get_draft(
            db,
            project_id,
            payload.candidate_id,
            payload.selected_title_order,
        )
        return serialize_draft(db, draft)
    except DraftError as exc:
        raise _bad_request(exc) from exc


@router.get("/api/drafts/{draft_id}", response_model=DraftResponse)
def read_draft(draft_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return serialize_draft(db, get_draft(db, draft_id))
    except DraftError as exc:
        raise _bad_request(exc) from exc


@router.patch("/api/drafts/{draft_id}", response_model=DraftResponse)
def patch_draft(draft_id: int, payload: DraftPatchRequest, db: Session = Depends(get_db)) -> dict:
    try:
        draft = get_draft(db, draft_id)
        values = payload.model_dump(exclude_unset=True)
        incoming_ranges = values.pop("title_highlight_ranges", None)
        title_changed = "custom_title" in values and values["custom_title"] != draft.custom_title
        next_title = values.get("custom_title", draft.custom_title)
        if title_changed:
            draft.title_highlight_ranges = "[]"
        elif incoming_ranges is not None:
            draft.title_highlight_ranges = dump_highlight_ranges(next_title, incoming_ranges)
        elif "title_highlight_text" in values:
            draft.title_highlight_ranges = dump_highlight_ranges(
                next_title,
                legacy_highlight_range(next_title, values["title_highlight_text"]),
            )
        for key, value in values.items():
            setattr(draft, key, value)
        db.commit()
        return serialize_draft(db, draft)
    except (DraftError, ValueError) as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.patch("/api/drafts/{draft_id}/range", response_model=DraftResponse)
def patch_draft_range(draft_id: int, payload: DraftRangeRequest, db: Session = Depends(get_db)) -> dict:
    try:
        draft = get_draft(db, draft_id)
        updated = update_draft_range(
            db,
            draft,
            payload.start_segment_id,
            payload.end_segment_id,
            payload.regenerate_subtitles,
        )
        return serialize_draft(db, updated)
    except DraftError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.put("/api/drafts/{draft_id}/subtitles", response_model=DraftResponse)
def put_subtitles(draft_id: int, payload: SubtitlePutRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return serialize_draft(db, save_subtitles(db, get_draft(db, draft_id), payload.subtitles))
    except DraftError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.patch("/api/drafts/{draft_id}/subtitles/{subtitle_id}", response_model=DraftResponse)
def patch_subtitle(
    draft_id: int,
    subtitle_id: int,
    payload: SubtitlePatchRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        draft = get_draft(db, draft_id)
        subtitle = db.get(DraftSubtitle, subtitle_id)
        if subtitle is None or subtitle.draft_id != draft.id:
            raise DraftError("삭제되었거나 존재하지 않는 자막입니다.")
        values = payload.model_dump(exclude_unset=True)
        for key, value in values.items():
            setattr(subtitle, key, value)
        subtitle.is_edited = subtitle.edited_text != subtitle.original_text
        validate_subtitle_sequence(draft, draft.subtitles)
        db.commit()
        return serialize_draft(db, draft)
    except DraftError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.post("/api/drafts/{draft_id}/subtitles/{subtitle_id}/split", response_model=DraftResponse)
def split_draft_subtitle(
    draft_id: int,
    subtitle_id: int,
    payload: SubtitleSplitRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        draft = split_subtitle(db, get_draft(db, draft_id), subtitle_id, payload.split_index)
        return serialize_draft(db, draft)
    except DraftError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.post("/api/drafts/{draft_id}/subtitles/merge", response_model=DraftResponse)
def merge_draft_subtitles(
    draft_id: int,
    payload: SubtitleMergeRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        draft = merge_subtitles(
            db,
            get_draft(db, draft_id),
            payload.first_subtitle_id,
            payload.second_subtitle_id,
        )
        return serialize_draft(db, draft)
    except DraftError as exc:
        db.rollback()
        raise _bad_request(exc) from exc


@router.post("/api/drafts/{draft_id}/subtitles/reset", response_model=DraftResponse)
def reset_draft_subtitles(draft_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        draft = get_draft(db, draft_id)
        regenerate_subtitles(db, draft)
        db.commit()
        return serialize_draft(db, draft)
    except DraftError as exc:
        db.rollback()
        raise _bad_request(exc) from exc
