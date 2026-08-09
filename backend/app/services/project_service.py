import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models import CandidateTitle, ClipCandidate, Project, TranscriptSegment, TranscriptWord
from app.schemas.analysis import StoredTranscriptSegmentData, TranscriptSegmentData, TranscriptionResult
from app.services.sermon_analysis_service import (
    MockSermonAnalysisService,
    OpenAISermonAnalysisService,
    SelectedCandidate,
    SermonAnalysisError,
    SermonAnalysisService,
    normalize_and_select_candidates,
)
from app.services.transcription_service import (
    MockTranscriptionService,
    OpenAITranscriptionService,
    TranscriptionError,
    TranscriptionService,
)
from app.services.video_service import VideoProcessingError, VideoService


logger = logging.getLogger(__name__)
TRANSCRIPT_FAILURE_MESSAGE = "실제 음성 대본을 생성하지 못해 쇼츠 후보 분석을 중단했습니다."


def update_status(db: Session, project: Project, status: str, progress: int) -> None:
    project.status = status
    project.progress = progress
    project.error_message = None
    project.error_stage = None
    db.commit()


def fail_project(db: Session, project: Project, message: str) -> None:
    failed_stage = project.status
    project.status = "failed"
    project.error_stage = failed_stage
    project.error_message = message
    db.commit()


def analyze_project(project_id: str) -> None:
    db = SessionLocal()
    project = db.get(Project, project_id)
    if project is None:
        db.close()
        return
    try:
        run_analysis_pipeline(db, project)
    except (VideoProcessingError, TranscriptionError, SermonAnalysisError) as exc:
        logger.warning("Project %s failed at %s: %s", project_id, project.status, exc)
        if project.status != "failed":
            fail_project(db, project, str(exc))
    except Exception:
        logger.exception("Unexpected analysis failure for project %s", project_id)
        fail_project(db, project, "분석 중 예기치 않은 오류가 발생했습니다. 다시 시도해 주세요.")
    finally:
        db.close()


def run_analysis_pipeline(
    db: Session,
    project: Project,
    video_service: Optional[VideoService] = None,
    transcription_service: Optional[TranscriptionService] = None,
    analysis_service: Optional[SermonAnalysisService] = None,
) -> None:
    settings = get_settings()
    project.analysis_mode = "mock" if settings.use_mock_ai else "real"
    project.transcription_model = "mock-transcription" if settings.use_mock_ai else settings.openai_transcribe_model
    db.commit()

    video_service = video_service or VideoService(
        settings.processed_dir,
        settings.audio_chunk_minutes,
        settings.audio_chunk_overlap_seconds,
    )
    update_status(db, project, "extracting_audio", 15)
    audio_path = video_service.extract_audio(Path(project.stored_file_path), project.id)
    video_service.validate_extracted_audio(audio_path, project.duration_seconds)
    update_status(db, project, "extracting_audio", 25)
    chunks = video_service.split_audio(audio_path, project.duration_seconds)

    update_status(db, project, "transcribing", 30)
    transcription_service = transcription_service or (
        MockTranscriptionService()
        if settings.use_mock_ai
        else OpenAITranscriptionService(settings.openai_api_key, settings.openai_transcribe_model)
    )
    try:
        transcription = transcription_service.transcribe(
            chunks,
            project.duration_seconds,
            on_progress=lambda progress: update_status(db, project, "transcribing", progress),
        )
        _validate_transcription_result(transcription)
        _replace_transcript(db, project, transcription.segments)
        stored_segments = _load_stored_transcript(db, project.id)
        _validate_stored_transcript(stored_segments, transcription)
        project.transcript_segment_count = len(stored_segments)
        project.transcript_char_count = sum(len(item.text) for item in stored_segments)
        db.commit()
    except TranscriptionError as exc:
        fail_project(db, project, str(exc))
        raise

    update_status(db, project, "analyzing", 70)
    analysis_service = analysis_service or (
        MockSermonAnalysisService()
        if settings.use_mock_ai
        else OpenAISermonAnalysisService(settings.openai_api_key, settings.openai_analysis_model)
    )
    analysis = analysis_service.analyze(stored_segments, project.duration_seconds)
    update_status(db, project, "analyzing", 85)
    selected = normalize_and_select_candidates(analysis, stored_segments, project.duration_seconds, limit=4)
    _replace_candidates(db, project, analysis.sermon_summary, analysis.sermon_topics, selected)
    update_status(db, project, "completed", 100)


def _validate_transcription_result(transcription: TranscriptionResult) -> None:
    if not transcription.text.strip() or not transcription.segments:
        raise TranscriptionError(TRANSCRIPT_FAILURE_MESSAGE)
    for segment in transcription.segments:
        if not segment.text.strip() or segment.end_sec <= segment.start_sec:
            raise TranscriptionError(TRANSCRIPT_FAILURE_MESSAGE)


def _load_stored_transcript(db: Session, project_id: str) -> List[StoredTranscriptSegmentData]:
    rows = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.segment_order)
    ).all()
    return [
        StoredTranscriptSegmentData(
            segment_id=row.id,
            segment_order=row.segment_order,
            start_sec=row.start_sec,
            end_sec=row.end_sec,
            text=row.text,
        )
        for row in rows
    ]


def _validate_stored_transcript(
    stored_segments: Sequence[StoredTranscriptSegmentData],
    transcription: TranscriptionResult,
) -> None:
    if len(stored_segments) != len(transcription.segments) or not stored_segments:
        raise TranscriptionError(TRANSCRIPT_FAILURE_MESSAGE)
    if any(not item.text.strip() or item.end_sec <= item.start_sec for item in stored_segments):
        raise TranscriptionError(TRANSCRIPT_FAILURE_MESSAGE)
    stored_text = " ".join(item.text for item in stored_segments)
    source_text = " ".join(item.text for item in transcription.segments)
    if stored_text != source_text:
        raise TranscriptionError(TRANSCRIPT_FAILURE_MESSAGE)


def _replace_transcript(db: Session, project: Project, segments: List[TranscriptSegmentData]) -> None:
    db.execute(delete(TranscriptWord).where(TranscriptWord.project_id == project.id))
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.project_id == project.id))
    db.flush()
    word_order = 0
    for segment_order, item in enumerate(sorted(segments, key=lambda segment: segment.start_sec)):
        segment = TranscriptSegment(
            project_id=project.id,
            start_sec=item.start_sec,
            end_sec=item.end_sec,
            text=item.text,
            segment_order=segment_order,
        )
        db.add(segment)
        db.flush()
        for item_word in item.words:
            db.add(TranscriptWord(
                project_id=project.id,
                segment_id=segment.id,
                word=item_word.word,
                start_sec=item_word.start_sec,
                end_sec=item_word.end_sec,
                word_order=word_order,
            ))
            word_order += 1
    db.commit()


def _replace_candidates(
    db: Session,
    project: Project,
    summary: str,
    topics: List[str],
    selected: Sequence[SelectedCandidate],
) -> None:
    old_ids = db.scalars(select(ClipCandidate.id).where(ClipCandidate.project_id == project.id)).all()
    if old_ids:
        db.execute(delete(CandidateTitle).where(CandidateTitle.candidate_id.in_(old_ids)))
    db.execute(delete(ClipCandidate).where(ClipCandidate.project_id == project.id))
    project.sermon_summary = summary
    project.sermon_topics = json.dumps(topics, ensure_ascii=False)

    previous_end = -1.0
    for order, selected_item in enumerate(selected, start=1):
        start_row = db.get(TranscriptSegment, selected_item.start_segment_id)
        end_row = db.get(TranscriptSegment, selected_item.end_segment_id)
        if (
            start_row is None
            or end_row is None
            or start_row.project_id != project.id
            or end_row.project_id != project.id
            or end_row.segment_order < start_row.segment_order
        ):
            raise SermonAnalysisError("후보가 참조한 실제 대본 세그먼트를 찾지 못했습니다.")
        segment_rows = db.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.project_id == project.id,
                TranscriptSegment.segment_order >= start_row.segment_order,
                TranscriptSegment.segment_order <= end_row.segment_order,
            )
            .order_by(TranscriptSegment.segment_order)
        ).all()
        expected_count = end_row.segment_order - start_row.segment_order + 1
        if len(segment_rows) != expected_count:
            raise SermonAnalysisError("후보 구간의 실제 대본 세그먼트가 일부 누락되었습니다.")
        start_sec = segment_rows[0].start_sec
        end_sec = segment_rows[-1].end_sec
        if start_sec < 0 or end_sec > project.duration_seconds or start_sec < previous_end:
            raise SermonAnalysisError("후보 시간이 영상 범위 밖이거나 서로 겹칩니다.")
        transcript = " ".join(row.text for row in segment_rows)
        item = selected_item.analysis
        candidate = ClipCandidate(
            project_id=project.id,
            candidate_order=order,
            recommendation_type=item.recommendation_type,
            start_segment_id=segment_rows[0].id,
            end_segment_id=segment_rows[-1].id,
            segment_count=len(segment_rows),
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=end_sec - start_sec,
            transcript=transcript,
            main_topic=item.main_topic,
            selection_reason=item.selection_reason,
            centrality_score=item.scores.centrality,
            standalone_score=item.scores.standalone,
            hook_score=item.scores.hook,
            emotional_score=item.scores.emotional_impact,
            overall_score=item.scores.overall,
        )
        db.add(candidate)
        db.flush()
        for title_order, title in enumerate(item.titles, start=1):
            db.add(CandidateTitle(
                candidate_id=candidate.id,
                title=title.title,
                title_type=title.type,
                title_order=title_order,
            ))
        previous_end = end_sec
    db.commit()


def project_to_dict(project: Project) -> Dict[str, object]:
    return {
        "project_id": project.id,
        "original_file_name": project.original_file_name,
        "stored_file_name": Path(project.stored_file_path).name,
        "duration_seconds": project.duration_seconds,
        "width": project.width,
        "height": project.height,
        "file_size": project.file_size,
        "status": project.status,
        "progress": project.progress,
        "error_message": project.error_message,
        "error_stage": project.error_stage,
        "analysis_mode": project.analysis_mode,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }
