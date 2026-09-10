from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models import ClipCandidate, Project, TranscriptSegment
from app.schemas.analysis import (
    AnalysisCandidate,
    AnalysisScores,
    AnalysisTitle,
    SermonAnalysisResult,
    StoredTranscriptSegmentData,
    TranscriptionResult,
)
from app.services.project_service import (
    TRANSCRIPT_FAILURE_MESSAGE,
    _replace_candidates,
    run_analysis_pipeline,
)
from app.services.sermon_analysis_service import (
    OpenAISermonAnalysisService,
    SelectedCandidate,
    SermonAnalysisError,
    normalize_and_select_candidates,
)
from app.services.transcription_service import OpenAITranscriptionService, TranscriptionError
from app.services.video_service import AudioChunk, VideoProcessingError, VideoService


def test_data_dir_derives_persistent_storage_paths(tmp_path):
    settings = Settings(
        _env_file=None, data_dir=tmp_path, upload_dir=None, processed_dir=None, database_url="",
    )
    assert settings.data_dir == tmp_path
    assert settings.upload_dir == tmp_path / "uploads"
    assert settings.processed_dir == tmp_path / "processed"
    assert settings.database_url == f"sqlite:///{tmp_path / 'sermon_shorts.db'}"


def test_subtitle_font_is_always_the_bundled_gothic_font(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        subtitle_font_path="./backend/assets/fonts/NanumMyeongjo-Regular.ttf",
        subtitle_font_name="NanumMyeongjo",
    )
    assert settings.subtitle_font_path.name == "NanumGothic-Bold.ttf"
    assert settings.subtitle_font_name == "NanumGothic"


def stored_segments(count: int = 24) -> list[StoredTranscriptSegmentData]:
    return [
        StoredTranscriptSegmentData(
            segment_id=index + 1,
            segment_order=index,
            start_sec=index * 10,
            end_sec=(index + 1) * 10,
            text=f"목사님 실제 발언 {index}",
        )
        for index in range(count)
    ]


def make_candidate(index: int, fake_transcript: Optional[str] = None) -> AnalysisCandidate:
    payload = {
        "start_segment_id": index * 6 + 1,
        "end_segment_id": index * 6 + 6,
        "main_topic": f"주제 {index}",
        "recommendation_type": "핵심 메시지",
        "selection_reason": "완결된 구간",
        "scores": {"centrality": 90, "standalone": 90, "hook": 85, "emotional_impact": 85, "overall": 88},
        "titles": [{"title": f"제목 {value}", "type": "질문형"} for value in range(3)],
    }
    if fake_transcript:
        payload["transcript"] = fake_transcript
    return AnalysisCandidate.model_validate(payload)


def test_candidate_post_processing_uses_segment_ids_bounds_overlap_and_length():
    segments = stored_segments()
    analysis = SermonAnalysisResult(
        sermon_summary="요약",
        sermon_topics=["믿음"],
        candidates=[make_candidate(index) for index in range(4)],
    )
    selected = normalize_and_select_candidates(analysis, segments, 240)
    assert len(selected) == 4
    for item in selected:
        assert 0 <= item.start_sec < item.end_sec <= 240
        assert 30 <= item.end_sec - item.start_sec <= 75
        assert item.start_sec == segments[item.start_segment_id - 1].start_sec
        assert item.end_sec == segments[item.end_segment_id - 1].end_sec
    for left, right in zip(selected, selected[1:]):
        assert left.end_sec <= right.start_sec


def test_candidate_transcript_ignores_ai_text_and_joins_database_verbatim(db_session, tmp_path):
    project = Project(
        id=str(uuid4()), original_file_name="sermon.mp4", stored_file_path=str(tmp_path / "sermon.mp4"),
        duration_seconds=120, width=1920, height=1080, file_size=1, status="analyzing", progress=85,
        analysis_mode="real",
    )
    db_session.add(project)
    rows = []
    for index, text in enumerate(["첫 번째 실제 문장입니다.", "둘째 실제 문장을 그대로 말했습니다.", "마지막 원문입니다."]):
        row = TranscriptSegment(
            project=project, start_sec=index * 20, end_sec=(index + 1) * 20,
            text=text, segment_order=index,
        )
        db_session.add(row)
        rows.append(row)
    db_session.commit()

    fake = "AI가 지어낸 가짜 직접 발언"
    analysis = make_candidate(0, fake_transcript=fake)
    selected = [SelectedCandidate(
        analysis=analysis,
        start_segment_id=rows[0].id,
        end_segment_id=rows[-1].id,
        start_sec=0,
        end_sec=60,
        segment_count=3,
    )]
    _replace_candidates(db_session, project, "요약", ["믿음"], selected)
    saved = db_session.scalar(select(ClipCandidate).where(ClipCandidate.project_id == project.id))
    assert saved is not None
    assert saved.transcript == "첫 번째 실제 문장입니다. 둘째 실제 문장을 그대로 말했습니다. 마지막 원문입니다."
    assert fake not in saved.transcript
    assert saved.start_sec == rows[0].start_sec
    assert saved.end_sec == rows[-1].end_sec
    assert saved.start_segment_id == rows[0].id
    assert saved.end_segment_id == rows[-1].id
    assert saved.segment_count == 3


def test_empty_real_transcription_fails_before_candidate_analysis(db_session, tmp_path):
    settings = get_settings()
    previous_mode = settings.use_mock_ai
    settings.use_mock_ai = False
    try:
        video_path = tmp_path / "video.mp4"
        audio_path = tmp_path / "audio.wav"
        video_path.write_bytes(b"video")
        audio_path.write_bytes(b"audio")
        project = Project(
            id=str(uuid4()), original_file_name="video.mp4", stored_file_path=str(video_path),
            duration_seconds=180, width=1920, height=1080, file_size=5, status="uploaded", progress=10,
            analysis_mode="real",
        )
        db_session.add(project)
        db_session.commit()
        video_service = MagicMock()
        video_service.extract_audio.return_value = audio_path
        video_service.split_audio.return_value = [AudioChunk(audio_path, 0)]
        transcription_service = MagicMock()
        transcription_service.transcribe.return_value = TranscriptionResult(text="", segments=[])
        analysis_service = MagicMock()

        with pytest.raises(TranscriptionError, match=TRANSCRIPT_FAILURE_MESSAGE):
            run_analysis_pipeline(
                db_session, project, video_service=video_service,
                transcription_service=transcription_service, analysis_service=analysis_service,
            )
        assert project.status == "failed"
        assert project.error_message == TRANSCRIPT_FAILURE_MESSAGE
        analysis_service.analyze.assert_not_called()
        assert db_session.scalars(select(ClipCandidate).where(ClipCandidate.project_id == project.id)).all() == []
    finally:
        settings.use_mock_ai = previous_mode


def test_ffmpeg_failure_has_safe_message(tmp_path):
    service = VideoService(tmp_path)
    with patch("subprocess.run", side_effect=__import__("subprocess").CalledProcessError(1, "ffmpeg")):
        with pytest.raises(VideoProcessingError, match="음성을 추출"):
            service.extract_audio(tmp_path / "video.mp4", "project")


def test_openai_transcription_receives_extracted_audio_file(tmp_path):
    service = OpenAITranscriptionService("test-key", "whisper-1")
    audio = tmp_path / "chunk-000.mp3"
    audio.write_bytes(b"actual ffmpeg audio bytes")
    response = SimpleNamespace(
        text="실제 전사",
        segments=[{"start": 0, "end": 10, "text": "실제 전사"}],
        words=[],
    )
    service.client.audio.transcriptions.create = MagicMock(return_value=response)
    result = service.transcribe([AudioChunk(audio, 0)], 10)
    assert result.text == "실제 전사"
    request = service.client.audio.transcriptions.create.call_args.kwargs
    assert Path(request["file"].name) == audio


def test_openai_transcription_failure_is_wrapped(tmp_path):
    service = OpenAITranscriptionService("test-key", "whisper-1")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    service.client.audio.transcriptions.create = MagicMock(side_effect=RuntimeError("secret upstream error"))
    with pytest.raises(TranscriptionError, match="전사 API"):
        service.transcribe([AudioChunk(audio, 0)], 60)


def test_openai_analysis_retries_once_and_fails_safely():
    service = OpenAISermonAnalysisService("test-key", "gpt-4.1-mini")
    service.client.beta.chat.completions.parse = MagicMock(side_effect=RuntimeError("bad response"))
    with pytest.raises(SermonAnalysisError, match="검증하지 못했습니다"):
        service.analyze(stored_segments(6), 60)
    assert service.client.beta.chat.completions.parse.call_count == 2


def test_openai_analysis_repairs_overlapping_candidates_once():
    service = OpenAISermonAnalysisService("test-key", "gpt-4.1-mini")
    overlapping = SermonAnalysisResult(
        sermon_summary="요약",
        sermon_topics=["믿음"],
        candidates=[make_candidate(0) for _ in range(4)],
    )
    repaired = SermonAnalysisResult(
        sermon_summary="요약",
        sermon_topics=["믿음"],
        candidates=[make_candidate(index) for index in range(4)],
    )
    service.client.beta.chat.completions.parse = MagicMock(side_effect=[
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=overlapping))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=repaired))]),
    ])

    result = service.analyze(stored_segments(), 240)

    assert result is repaired
    assert service.client.beta.chat.completions.parse.call_count == 2
    repair_prompt = service.client.beta.chat.completions.parse.call_args_list[1].kwargs["messages"][1]["content"]
    assert "이전 후보안은 최종 4개가 서로 겹치거나" in repair_prompt
