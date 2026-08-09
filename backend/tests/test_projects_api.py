import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.models import (
    CandidateTitle,
    ClipCandidate,
    ClipDraft,
    DraftSubtitle,
    Project,
    RenderJob,
    TranscriptSegment,
)


def upload(client, path: Path, content_type: str = "video/mp4"):
    with path.open("rb") as source:
        return client.post("/api/projects", files={"file": (path.name, source, content_type)})


def test_health_checks_database_storage_ffmpeg_and_frontend(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "database": "ok", "storage": "ok", "ffmpeg": "ok", "frontend": "ok",
    }


def test_normal_mp4_upload_and_project_lookup(client, sample_video):
    response = upload(client, sample_video)
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "uploaded"
    assert payload["analysis_mode"] in {"mock", "real"}
    assert payload["duration_seconds"] > 2
    assert payload["width"] == 320
    assert payload["original_file_name"] == "sample.mp4"
    lookup = client.get(f"/api/projects/{payload['project_id']}")
    assert lookup.status_code == 200
    assert lookup.json()["project_id"] == payload["project_id"]


def test_rejects_non_mp4(client, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not video")
    response = upload(client, path, "text/plain")
    assert response.status_code == 415


def test_rejects_corrupt_video(client, tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not an mp4")
    response = upload(client, path)
    assert response.status_code == 422
    assert "읽을 수 없는" in response.json()["detail"]


def test_rejects_video_without_audio(client, silent_video):
    response = upload(client, silent_video)
    assert response.status_code == 422
    assert "오디오 트랙" in response.json()["detail"]


def seed_completed_project(db_session, tmp_path: Path) -> Project:
    video = tmp_path / "uploads" / f"{uuid4()}.mp4"
    video.write_bytes(b"video")
    project = Project(
        id=str(uuid4()), original_file_name="sermon.mp4", stored_file_path=str(video),
        duration_seconds=240, width=1920, height=1080, file_size=5,
        status="completed", progress=100, sermon_summary="요약", sermon_topics=json.dumps(["믿음"], ensure_ascii=False),
        analysis_mode="mock", transcription_model="mock-transcription", transcript_segment_count=4, transcript_char_count=16,
    )
    db_session.add(project)
    for index in range(4):
        segment = TranscriptSegment(project=project, start_sec=index * 60, end_sec=index * 60 + 60, text=f"대본 {index}", segment_order=index)
        db_session.add(segment)
        candidate = ClipCandidate(
            project=project, candidate_order=index + 1, recommendation_type="핵심 메시지",
            start_sec=index * 60, end_sec=index * 60 + 60, duration_sec=60,
            transcript=f"대본 {index}", main_topic=f"주제 {index}", selection_reason="이유",
            centrality_score=90, standalone_score=89, hook_score=88, emotional_score=87, overall_score=89,
        )
        db_session.add(candidate)
        db_session.flush()
        for title_index in range(3):
            db_session.add(CandidateTitle(candidate=candidate, title=f"제목 {title_index}", title_type="질문형", title_order=title_index + 1))
    db_session.commit()
    return project


def test_transcript_and_candidates_endpoints(client, db_session, tmp_path):
    project = seed_completed_project(db_session, tmp_path)
    transcript = client.get(f"/api/projects/{project.id}/transcript")
    candidates = client.get(f"/api/projects/{project.id}/candidates")
    assert transcript.status_code == 200
    assert len(transcript.json()["segments"]) == 4
    assert candidates.status_code == 200
    payload = candidates.json()
    assert payload["sermon_summary"] == "요약"
    assert payload["analysis_mode"] == "mock"
    assert payload["debug"]["transcription_model"] == "mock-transcription"
    assert len(payload["candidates"]) == 4
    assert len(payload["candidates"][0]["titles"]) == 3


def test_delete_removes_database_and_files(client, db_session, tmp_path):
    project = seed_completed_project(db_session, tmp_path)
    video_path = Path(project.stored_file_path)
    processed = tmp_path / "processed" / project.id
    processed.mkdir()
    (processed / "audio.wav").write_bytes(b"audio")
    response = client.delete(f"/api/projects/{project.id}")
    assert response.status_code == 204
    assert not video_path.exists()
    assert not processed.exists()
    assert db_session.get(Project, project.id) is None


def test_delete_removes_draft_subtitles_all_render_versions_and_preserves_other_project(client, db_session, tmp_path):
    project = seed_completed_project(db_session, tmp_path)
    other_project = seed_completed_project(db_session, tmp_path)
    segment = db_session.scalar(
        select(TranscriptSegment).where(TranscriptSegment.project_id == project.id).order_by(TranscriptSegment.id)
    )
    candidate = db_session.scalar(
        select(ClipCandidate).where(ClipCandidate.project_id == project.id).order_by(ClipCandidate.id)
    )
    assert segment is not None and candidate is not None
    candidate.start_segment_id = segment.id
    candidate.end_segment_id = segment.id
    draft = ClipDraft(
        project_id=project.id, candidate_id=candidate.id,
        start_segment_id=segment.id, end_segment_id=segment.id,
        start_sec=segment.start_sec, end_sec=segment.end_sec,
        duration_sec=segment.end_sec - segment.start_sec,
    )
    db_session.add(draft)
    db_session.flush()
    subtitle = DraftSubtitle(
        draft_id=draft.id, cue_order=1, start_sec=segment.start_sec, end_sec=segment.end_sec,
        original_text=segment.text, edited_text=segment.text,
    )
    db_session.add(subtitle)
    processed = tmp_path / "processed" / project.id
    renders_dir = processed / "renders"
    renders_dir.mkdir(parents=True)
    for version in range(1, 4):
        output = renders_dir / f"v{version}.mp4"
        output.write_bytes(f"render-{version}".encode())
        db_session.add(RenderJob(
            project_id=project.id, draft_id=draft.id, version=version,
            status="completed", progress=100, current_step="finalizing",
            output_file_path=str(output), output_file_name=output.name,
            output_file_size=output.stat().st_size, settings_snapshot="{}",
        ))
    other_processed = tmp_path / "processed" / other_project.id
    other_processed.mkdir(parents=True)
    other_file = other_processed / "keep.wav"
    other_file.write_bytes(b"keep")
    shared_file = tmp_path / "processed" / "shared-asset.png"
    shared_file.write_bytes(b"shared")
    db_session.commit()

    response = client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 204
    assert db_session.get(Project, project.id) is None
    assert db_session.scalar(select(func.count()).select_from(ClipDraft).where(ClipDraft.project_id == project.id)) == 0
    assert db_session.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.project_id == project.id)) == 0
    assert not processed.exists()
    assert db_session.get(Project, other_project.id) is not None
    assert Path(other_project.stored_file_path).exists()
    assert other_file.read_bytes() == b"keep"
    assert shared_file.read_bytes() == b"shared"


def test_delete_rejects_active_render_without_removing_project(client, db_session, tmp_path):
    project = seed_completed_project(db_session, tmp_path)
    segment = db_session.scalar(select(TranscriptSegment).where(TranscriptSegment.project_id == project.id))
    candidate = db_session.scalar(select(ClipCandidate).where(ClipCandidate.project_id == project.id))
    assert segment is not None and candidate is not None
    draft = ClipDraft(
        project_id=project.id, candidate_id=candidate.id,
        start_segment_id=segment.id, end_segment_id=segment.id,
        start_sec=segment.start_sec, end_sec=segment.end_sec,
        duration_sec=segment.end_sec - segment.start_sec,
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add(RenderJob(
        project_id=project.id, draft_id=draft.id, version=1,
        status="rendering", progress=50, current_step="encoding", settings_snapshot="{}",
    ))
    db_session.commit()

    response = client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 409
    assert "생성이 진행 중" in response.json()["detail"]
    assert db_session.get(Project, project.id) is not None
    assert Path(project.stored_file_path).exists()


def test_delete_rejects_file_outside_upload_root(client, db_session, tmp_path):
    project = seed_completed_project(db_session, tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    project.stored_file_path = str(outside)
    db_session.commit()

    response = client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 409
    assert "안전하게 확인" in response.json()["detail"]
    assert outside.read_bytes() == b"outside"
    assert db_session.get(Project, project.id) is not None
