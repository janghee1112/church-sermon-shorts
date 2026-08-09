import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.template_defaults import (
    SERMON_LETTERBOX_CROP_POSITION_X,
    SERMON_LETTERBOX_CROP_POSITION_Y,
    SERMON_LETTERBOX_PLAYBACK_RATE,
    SERMON_LETTERBOX_SUBTITLE_FONT_SCALE,
    SERMON_LETTERBOX_SUBTITLE_POSITION_Y,
    SERMON_LETTERBOX_TITLE_FONT_SCALE,
    SERMON_LETTERBOX_TITLE_POSITION_Y,
    SERMON_LETTERBOX_VIDEO_AREA_POSITION_Y,
    SERMON_LETTERBOX_ZOOM_SCALE,
)
from app.models import CandidateTitle, ClipCandidate, ClipDraft, DraftSubtitle, Project, TranscriptSegment, TranscriptWord
from app.schemas.drafts import SubtitleSaveItem
from app.services.title_highlight import legacy_highlight_range, load_highlight_ranges


class DraftError(Exception):
    pass


@dataclass(frozen=True)
class SubtitleUnit:
    text: str
    start_sec: float
    end_sec: float


def get_project_candidate(db: Session, project_id: str, candidate_id: int) -> Tuple[Project, ClipCandidate]:
    project = db.get(Project, project_id)
    if project is None:
        raise DraftError("프로젝트를 찾을 수 없습니다.")
    candidate = db.get(ClipCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise DraftError("후보를 찾을 수 없습니다.")
    return project, candidate


def resolve_candidate_segments(
    db: Session, candidate: ClipCandidate
) -> Tuple[TranscriptSegment, TranscriptSegment]:
    start = db.get(TranscriptSegment, candidate.start_segment_id) if candidate.start_segment_id else None
    end = db.get(TranscriptSegment, candidate.end_segment_id) if candidate.end_segment_id else None
    if start is None or start.project_id != candidate.project_id:
        start = _nearest_segment(db, candidate.project_id, candidate.start_sec, use_end=False)
    if end is None or end.project_id != candidate.project_id:
        end = _nearest_segment(db, candidate.project_id, candidate.end_sec, use_end=True)
    if start is None or end is None:
        raise DraftError("실제 전사 세그먼트가 없어 편집 초안을 만들 수 없습니다.")
    if start.segment_order > end.segment_order:
        raise DraftError("후보의 시작 문장이 종료 문장보다 뒤에 있습니다.")
    return start, end


def validate_range_segments(
    db: Session, project_id: str, start_segment_id: int, end_segment_id: int
) -> Tuple[TranscriptSegment, TranscriptSegment]:
    start = db.get(TranscriptSegment, start_segment_id)
    end = db.get(TranscriptSegment, end_segment_id)
    if start is None or end is None:
        raise DraftError("존재하지 않는 전사 세그먼트입니다.")
    if start.project_id != project_id or end.project_id != project_id:
        raise DraftError("다른 프로젝트의 전사 세그먼트는 사용할 수 없습니다.")
    if start.segment_order > end.segment_order:
        raise DraftError("시작 문장은 종료 문장보다 뒤에 올 수 없습니다.")
    return start, end


def _selected_candidate_title(
    db: Session, candidate_id: int, selected_title_order: Optional[int]
) -> str:
    if selected_title_order is None:
        return ""
    title = db.scalar(
        select(CandidateTitle.title).where(
            CandidateTitle.candidate_id == candidate_id,
            CandidateTitle.title_order == selected_title_order,
        )
    )
    if title is None:
        raise DraftError("선택한 추천 제목을 찾을 수 없습니다.")
    return title


def create_or_get_draft(
    db: Session,
    project_id: str,
    candidate_id: int,
    selected_title_order: Optional[int] = None,
) -> ClipDraft:
    project, candidate = get_project_candidate(db, project_id, candidate_id)
    selected_title = _selected_candidate_title(db, candidate_id, selected_title_order)
    existing = db.scalar(
        select(ClipDraft).where(ClipDraft.candidate_id == candidate_id)
    )
    if existing is not None:
        if selected_title and selected_title != existing.custom_title:
            existing.custom_title = selected_title
            existing.title_highlight_ranges = "[]"
            db.commit()
            db.refresh(existing)
        return existing
    start, end = resolve_candidate_segments(db, candidate)
    draft = ClipDraft(
        project_id=project.id,
        candidate_id=candidate.id,
        start_segment_id=start.id,
        end_segment_id=end.id,
        start_sec=start.start_sec,
        end_sec=end.end_sec,
        duration_sec=end.end_sec - start.start_sec,
        custom_title=selected_title,
        title_highlight_text="",
        title_highlight_ranges="[]",
        zoom_scale=SERMON_LETTERBOX_ZOOM_SCALE,
        crop_position_x=SERMON_LETTERBOX_CROP_POSITION_X,
        crop_position_y=SERMON_LETTERBOX_CROP_POSITION_Y,
        video_area_position_y=SERMON_LETTERBOX_VIDEO_AREA_POSITION_Y,
        video_area_height=0.48,
        title_font_scale=SERMON_LETTERBOX_TITLE_FONT_SCALE,
        title_position_y=SERMON_LETTERBOX_TITLE_POSITION_Y,
        subtitle_font_scale=SERMON_LETTERBOX_SUBTITLE_FONT_SCALE,
        subtitle_position_y=SERMON_LETTERBOX_SUBTITLE_POSITION_Y,
        playback_rate=SERMON_LETTERBOX_PLAYBACK_RATE,
        template_type="sermon_letterbox_v1",
        status="editing",
    )
    db.add(draft)
    db.flush()
    regenerate_subtitles(db, draft)
    db.commit()
    db.refresh(draft)
    return draft


def get_draft(db: Session, draft_id: int) -> ClipDraft:
    draft = db.scalar(
        select(ClipDraft)
        .where(ClipDraft.id == draft_id)
        .options(selectinload(ClipDraft.subtitles), selectinload(ClipDraft.project), selectinload(ClipDraft.candidate))
    )
    if draft is None:
        raise DraftError("편집 초안을 찾을 수 없습니다.")
    return draft


def update_draft_range(
    db: Session,
    draft: ClipDraft,
    start_segment_id: int,
    end_segment_id: int,
    regenerate: bool,
) -> ClipDraft:
    start, end = validate_range_segments(db, draft.project_id, start_segment_id, end_segment_id)
    if start.start_sec < 0 or end.end_sec > draft.project.duration_seconds:
        raise DraftError("선택한 구간이 영상 범위를 벗어났습니다.")
    draft.start_segment_id = start.id
    draft.end_segment_id = end.id
    draft.start_sec = start.start_sec
    draft.end_sec = end.end_sec
    draft.duration_sec = end.end_sec - start.start_sec
    if regenerate:
        regenerate_subtitles(db, draft)
    db.commit()
    return get_draft(db, draft.id)


def regenerate_subtitles(db: Session, draft: ClipDraft) -> List[DraftSubtitle]:
    start, end = validate_range_segments(
        db, draft.project_id, draft.start_segment_id, draft.end_segment_id
    )
    segments = db.scalars(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.project_id == draft.project_id,
            TranscriptSegment.segment_order >= start.segment_order,
            TranscriptSegment.segment_order <= end.segment_order,
        )
        .options(selectinload(TranscriptSegment.words))
        .order_by(TranscriptSegment.segment_order)
    ).all()
    if not segments:
        raise DraftError("자막을 만들 실제 전사 세그먼트가 없습니다.")
    db.execute(delete(DraftSubtitle).where(DraftSubtitle.draft_id == draft.id))
    draft.updated_at = datetime.now(timezone.utc)
    all_units: List[SubtitleUnit] = []
    for segment in segments:
        all_units.extend(_units_for_segment(segment))
    grouped = [
        (text, max(draft.start_sec, cue_start), min(draft.end_sec, cue_end))
        for text, cue_start, cue_end in _group_units(all_units)
    ]
    if len(grouped) > 1 and grouped[-1][2] - grouped[-1][1] < 1.0:
        previous = grouped[-2]
        orphan = grouped[-1]
        grouped[-2:] = [(_join_text(previous[0], orphan[0]), previous[1], orphan[2])]
    cues: List[DraftSubtitle] = []
    for text, cue_start, cue_end in grouped:
        cue = DraftSubtitle(
            draft_id=draft.id,
            cue_order=len(cues) + 1,
            start_sec=cue_start,
            end_sec=cue_end,
            original_text=text,
            edited_text=text,
            is_edited=False,
        )
        if cue.end_sec > cue.start_sec:
            db.add(cue)
            cues.append(cue)
    db.flush()
    validate_subtitle_sequence(draft, cues)
    return cues


def save_subtitles(db: Session, draft: ClipDraft, items: Sequence[SubtitleSaveItem]) -> ClipDraft:
    existing = {item.id: item for item in draft.subtitles}
    if set(existing) != {item.id for item in items}:
        raise DraftError("삭제되었거나 존재하지 않는 자막이 포함되어 있습니다.")
    ordered = sorted(items, key=lambda item: item.cue_order)
    if [item.cue_order for item in ordered] != list(range(1, len(ordered) + 1)):
        raise DraftError("자막 순서는 1부터 연속되어야 합니다.")
    for item in ordered:
        subtitle = existing[item.id]
        subtitle.cue_order = item.cue_order
        subtitle.start_sec = item.start_sec
        subtitle.end_sec = item.end_sec
        subtitle.edited_text = item.edited_text
        subtitle.is_edited = subtitle.edited_text != subtitle.original_text
    validate_subtitle_sequence(draft, list(existing.values()))
    db.commit()
    return get_draft(db, draft.id)


def validate_subtitle_sequence(draft: ClipDraft, subtitles: Sequence[DraftSubtitle]) -> None:
    ordered = sorted(subtitles, key=lambda item: item.cue_order)
    if not ordered:
        raise DraftError("저장할 자막이 없습니다.")
    previous_end = draft.start_sec
    for expected_order, subtitle in enumerate(ordered, start=1):
        if subtitle.cue_order != expected_order:
            raise DraftError("자막 순서가 연속적이지 않습니다.")
        if subtitle.start_sec < draft.start_sec - 0.01 or subtitle.end_sec > draft.end_sec + 0.01:
            raise DraftError("자막 시간이 선택 구간을 벗어났습니다.")
        if subtitle.end_sec <= subtitle.start_sec:
            raise DraftError("자막 종료 시간은 시작 시간보다 뒤여야 합니다.")
        if subtitle.start_sec < previous_end - 0.15:
            raise DraftError("자막 시간이 비정상적으로 겹칩니다.")
        previous_end = subtitle.end_sec


def split_subtitle(db: Session, draft: ClipDraft, subtitle_id: int, split_index: int) -> ClipDraft:
    subtitle = db.get(DraftSubtitle, subtitle_id)
    if subtitle is None or subtitle.draft_id != draft.id:
        raise DraftError("삭제되었거나 존재하지 않는 자막입니다.")
    edited_left, edited_right, actual_index = _split_text(subtitle.edited_text, split_index)
    ratio = actual_index / max(1, len(subtitle.edited_text))
    original_index = _nearest_boundary(subtitle.original_text, round(len(subtitle.original_text) * ratio))
    original_left, original_right, _ = _split_text(subtitle.original_text, original_index)
    first_end, second_start = _split_times_with_words(db, draft, subtitle, ratio)
    if first_end <= subtitle.start_sec or second_start >= subtitle.end_sec:
        raise DraftError("자막 길이가 너무 짧아 나눌 수 없습니다.")
    old_end = subtitle.end_sec
    subtitle.original_text = original_left
    subtitle.edited_text = edited_left
    subtitle.end_sec = first_end
    subtitle.is_edited = edited_left != original_left
    for item in draft.subtitles:
        if item.cue_order > subtitle.cue_order:
            item.cue_order += 1
    created = DraftSubtitle(
        draft_id=draft.id,
        cue_order=subtitle.cue_order + 1,
        start_sec=second_start,
        end_sec=old_end,
        original_text=original_right,
        edited_text=edited_right,
        is_edited=edited_right != original_right,
    )
    db.add(created)
    db.commit()
    return get_draft(db, draft.id)


def merge_subtitles(db: Session, draft: ClipDraft, first_id: int, second_id: int) -> ClipDraft:
    first = db.get(DraftSubtitle, first_id)
    second = db.get(DraftSubtitle, second_id)
    if first is None or second is None or first.draft_id != draft.id or second.draft_id != draft.id:
        raise DraftError("삭제되었거나 존재하지 않는 자막입니다.")
    if second.cue_order != first.cue_order + 1:
        raise DraftError("서로 인접한 자막만 합칠 수 있습니다.")
    first.end_sec = second.end_sec
    first.original_text = _join_text(first.original_text, second.original_text)
    first.edited_text = _join_text(first.edited_text, second.edited_text)
    first.is_edited = first.edited_text != first.original_text
    removed_order = second.cue_order
    db.delete(second)
    for item in draft.subtitles:
        if item.id != second.id and item.cue_order > removed_order:
            item.cue_order -= 1
    db.commit()
    return get_draft(db, draft.id)


def serialize_draft(db: Session, draft: ClipDraft) -> dict:
    draft = get_draft(db, draft.id)
    recommended_start, recommended_end = resolve_candidate_segments(db, draft.candidate)
    placeholder = db.scalar(
        select(CandidateTitle.title)
        .where(CandidateTitle.candidate_id == draft.candidate_id)
        .order_by(CandidateTitle.title_order)
        .limit(1)
    ) or ""
    return {
        "id": draft.id,
        "project_id": draft.project_id,
        "project_original_file_name": draft.project.original_file_name,
        "analysis_mode": draft.project.analysis_mode,
        "candidate_id": draft.candidate_id,
        "candidate": {
            "id": draft.candidate.id,
            "candidate_order": draft.candidate.candidate_order,
            "main_topic": draft.candidate.main_topic,
            "recommended_start_segment_id": recommended_start.id,
            "recommended_end_segment_id": recommended_end.id,
            "recommended_start_sec": recommended_start.start_sec,
            "recommended_end_sec": recommended_end.end_sec,
            "title_placeholder": placeholder,
        },
        "range": {
            "start_segment_id": draft.start_segment_id,
            "end_segment_id": draft.end_segment_id,
            "start_sec": draft.start_sec,
            "end_sec": draft.end_sec,
            "duration_sec": draft.duration_sec,
        },
        "custom_title": draft.custom_title,
        "title_highlight_text": draft.title_highlight_text,
        "title_highlight_ranges": load_highlight_ranges(draft.custom_title, draft.title_highlight_ranges),
        "zoom_scale": draft.zoom_scale,
        "crop_position_x": draft.crop_position_x,
        "crop_position_y": draft.crop_position_y,
        "video_area_position_y": draft.video_area_position_y,
        "video_area_height": draft.video_area_height,
        "title_font_scale": draft.title_font_scale,
        "title_position_y": draft.title_position_y,
        "subtitle_font_scale": draft.subtitle_font_scale,
        "subtitle_position_y": draft.subtitle_position_y,
        "playback_rate": draft.playback_rate,
        "template_type": draft.template_type,
        "status": draft.status,
        "subtitles": [
            {
                "id": item.id,
                "cue_order": item.cue_order,
                "start_sec": item.start_sec,
                "end_sec": item.end_sec,
                "relative_start_sec": item.start_sec - draft.start_sec,
                "relative_end_sec": item.end_sec - draft.start_sec,
                "original_text": item.original_text,
                "edited_text": item.edited_text,
                "is_edited": item.is_edited,
            }
            for item in sorted(draft.subtitles, key=lambda value: value.cue_order)
        ],
        "updated_at": draft.updated_at,
    }


def _nearest_segment(db: Session, project_id: str, seconds: float, use_end: bool) -> TranscriptSegment:
    segments = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order)
    ).all()
    if not segments:
        raise DraftError("실제 전사 세그먼트가 없습니다.")
    return min(segments, key=lambda item: abs((item.end_sec if use_end else item.start_sec) - seconds))


def _units_for_segment(segment: TranscriptSegment) -> List[SubtitleUnit]:
    words = sorted(segment.words, key=lambda item: item.word_order)
    if words:
        return [SubtitleUnit(f"{item.word} ", item.start_sec, item.end_sec) for item in words]
    pieces = [match.group(0) for match in re.finditer(r"\S+\s*", segment.text)] or [segment.text]
    total_weight = sum(max(1, len(piece.strip())) for piece in pieces)
    elapsed = segment.start_sec
    units: List[SubtitleUnit] = []
    for index, piece in enumerate(pieces):
        weight = max(1, len(piece.strip()))
        duration = (segment.end_sec - segment.start_sec) * weight / total_weight
        end = segment.end_sec if index == len(pieces) - 1 else elapsed + duration
        units.append(SubtitleUnit(piece, elapsed, end))
        elapsed = end
    return units


def _group_units(units: Sequence[SubtitleUnit]) -> List[Tuple[str, float, float]]:
    groups: List[Tuple[str, float, float]] = []
    current: List[SubtitleUnit] = []
    for unit in units:
        projected = "".join(item.text for item in current + [unit]).strip()
        duration = unit.end_sec - (current[0].start_sec if current else unit.start_sec)
        current_duration = current[-1].end_sec - current[0].start_sec if current else 0
        if current and current_duration >= 1.0 and (len(projected) > 30 or duration > 4.0):
            groups.append(_finish_group(current))
            current = []
        current.append(unit)
        current_text = "".join(item.text for item in current).strip()
        current_duration = current[-1].end_sec - current[0].start_sec
        if current_duration >= 1.0 and re.search(r"[.!?。！？]$", current_text):
            groups.append(_finish_group(current))
            current = []
    if current:
        groups.append(_finish_group(current))
    if len(groups) > 1 and groups[-1][2] - groups[-1][1] < 1.0:
        previous = groups[-2]
        orphan = groups[-1]
        groups[-2:] = [(_join_text(previous[0], orphan[0]), previous[1], orphan[2])]
    return groups


def _finish_group(units: Sequence[SubtitleUnit]) -> Tuple[str, float, float]:
    return "".join(item.text for item in units).strip(), units[0].start_sec, units[-1].end_sec


def _split_text(text: str, index: int) -> Tuple[str, str, int]:
    boundary = _nearest_boundary(text, index)
    left = text[:boundary].strip()
    right = text[boundary:].strip()
    if not left or not right:
        raise DraftError("자막은 단어 또는 어절 경계에서 나눠 주세요.")
    return left, right, boundary


def _nearest_boundary(text: str, index: int) -> int:
    boundaries = [match.start() for match in re.finditer(r"\s+", text)]
    if not boundaries:
        return max(1, min(len(text) - 1, index))
    return min(boundaries, key=lambda value: abs(value - index))


def _split_times_with_words(
    db: Session, draft: ClipDraft, subtitle: DraftSubtitle, ratio: float
) -> Tuple[float, float]:
    words = db.scalars(
        select(TranscriptWord)
        .where(
            TranscriptWord.project_id == draft.project_id,
            TranscriptWord.start_sec >= subtitle.start_sec - 0.01,
            TranscriptWord.end_sec <= subtitle.end_sec + 0.01,
        )
        .order_by(TranscriptWord.word_order)
    ).all()
    if len(words) >= 2:
        split_at = min(len(words) - 1, max(1, round(len(words) * ratio)))
        return words[split_at - 1].end_sec, words[split_at].start_sec
    split_time = subtitle.start_sec + (subtitle.end_sec - subtitle.start_sec) * ratio
    minimum = min(0.3, (subtitle.end_sec - subtitle.start_sec) / 3)
    split_time = max(subtitle.start_sec + minimum, min(subtitle.end_sec - minimum, split_time))
    return split_time, split_time


def _join_text(first: str, second: str) -> str:
    return f"{first.rstrip()} {second.lstrip()}".strip()
