from uuid import uuid4
import json
from typing import Optional

import pytest
from sqlalchemy import create_engine, inspect, text
from pydantic import ValidationError

from app.database.session import _add_mvp_columns
from app.models import CandidateTitle, ClipCandidate, ClipDraft, DraftSubtitle, Project, TranscriptSegment
from app.schemas.drafts import DraftPatchRequest


def seed_draft_source(db_session, *, project_id: Optional[str] = None):
    project = Project(
        id=project_id or str(uuid4()), original_file_name="sermon.mp4", stored_file_path="/tmp/sermon.mp4",
        duration_seconds=120, width=1920, height=1080, file_size=10, status="completed", progress=100,
        analysis_mode="real", transcription_model="gpt-test", transcript_segment_count=8, transcript_char_count=100,
    )
    db_session.add(project)
    segments = []
    for index in range(8):
        segment = TranscriptSegment(
            project=project, start_sec=index * 10.0, end_sec=(index + 1) * 10.0,
            text=f"실제 설교 문장 {index + 1} 입니다.", segment_order=index + 1,
        )
        db_session.add(segment)
        segments.append(segment)
    db_session.flush()
    candidate = ClipCandidate(
        project=project, candidate_order=1, recommendation_type="핵심 메시지",
        start_segment_id=segments[1].id, end_segment_id=segments[6].id, segment_count=6,
        start_sec=segments[1].start_sec, end_sec=segments[6].end_sec, duration_sec=60,
        transcript=" ".join(item.text for item in segments[1:7]), main_topic="믿음", selection_reason="완결성",
        centrality_score=90, standalone_score=90, hook_score=85, emotional_score=88, overall_score=89,
    )
    db_session.add(candidate)
    db_session.flush()
    for order, title in enumerate(("믿음으로 사는 법", "걱정보다 믿음을 선택하세요", "하나님을 신뢰하는 하루"), start=1):
        db_session.add(CandidateTitle(candidate=candidate, title=title, title_type="단정형", title_order=order))
    db_session.commit()
    return project, candidate, segments


def create_draft(client, project, candidate, selected_title_order=None):
    payload = {"candidate_id": candidate.id}
    if selected_title_order is not None:
        payload["selected_title_order"] = selected_title_order
    return client.post(f"/api/projects/{project.id}/drafts", json=payload)


def test_create_is_idempotent_and_uses_candidate_boundaries(client, db_session):
    project, candidate, segments = seed_draft_source(db_session)
    first = create_draft(client, project, candidate)
    second = create_draft(client, project, candidate)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    payload = first.json()
    assert payload["range"]["start_segment_id"] == segments[1].id
    assert payload["range"]["end_segment_id"] == segments[6].id
    assert payload["range"]["start_sec"] == segments[1].start_sec
    assert payload["range"]["end_sec"] == segments[6].end_sec
    assert payload["candidate"]["title_placeholder"] == "믿음으로 사는 법"
    assert [item["cue_order"] for item in payload["subtitles"]] == list(range(1, len(payload["subtitles"]) + 1))
    assert all(payload["range"]["start_sec"] <= item["start_sec"] < item["end_sec"] <= payload["range"]["end_sec"] for item in payload["subtitles"])
    generated_words = " ".join(item["original_text"] for item in payload["subtitles"]).split()
    source_words = " ".join(item.text for item in segments[1:7]).split()
    assert generated_words == source_words
    assert payload["zoom_scale"] == 1.30
    assert payload["crop_position_x"] == 0.5
    assert payload["crop_position_y"] == 0.42
    assert payload["video_area_position_y"] == 0.28
    assert payload["video_area_height"] == 0.48
    assert payload["title_highlight_text"] == ""
    assert payload["title_highlight_ranges"] == []
    assert payload["title_font_scale"] == 1.20
    assert payload["title_position_y"] == 0.08
    assert payload["subtitle_font_scale"] == 1.0
    assert payload["subtitle_position_y"] == 0.24
    assert payload["playback_rate"] == 1.20
    assert "background_darkness" not in payload
    assert "subject_brightness" not in payload
    assert "subject_mask_enabled" not in payload
    assert payload["template_type"] == "sermon_letterbox_v1"


def test_selected_recommended_title_becomes_draft_title(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    response = create_draft(client, project, candidate, selected_title_order=2)
    assert response.status_code == 201
    assert response.json()["custom_title"] == "걱정보다 믿음을 선택하세요"
    assert db_session.get(ClipDraft, response.json()["id"]).custom_title == "걱정보다 믿음을 선택하세요"


def test_selected_title_updates_an_existing_draft_only_when_explicitly_selected(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    created = create_draft(client, project, candidate).json()
    filled = create_draft(client, project, candidate, selected_title_order=3).json()
    assert filled["id"] == created["id"]
    assert filled["custom_title"] == "하나님을 신뢰하는 하루"

    client.patch(f"/api/drafts/{created['id']}", json={"custom_title": "직접 입력한 제목"})
    preserved = create_draft(client, project, candidate).json()
    assert preserved["custom_title"] == "직접 입력한 제목"
    replaced = create_draft(client, project, candidate, selected_title_order=1).json()
    assert replaced["custom_title"] == "믿음으로 사는 법"


def test_draft_get_and_persistence(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    created = create_draft(client, project, candidate).json()
    response = client.patch(f"/api/drafts/{created['id']}", json={"custom_title": "새 제목", "crop_position_x": 0.25, "status": "ready"})
    assert response.status_code == 200
    loaded = client.get(f"/api/drafts/{created['id']}").json()
    assert loaded["custom_title"] == "새 제목"
    assert loaded["crop_position_x"] == 0.25
    assert loaded["status"] == "ready"
    assert db_session.get(ClipDraft, created["id"]).custom_title == "새 제목"


def test_playback_rate_validates_persists_and_loads(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate).json()["id"]
    for rate in (0.9, 1.2, 1.5, 1.0):
        saved = client.patch(f"/api/drafts/{draft_id}", json={"playback_rate": rate})
        assert saved.status_code == 200
        assert saved.json()["playback_rate"] == rate
        assert client.get(f"/api/drafts/{draft_id}").json()["playback_rate"] == rate
    for invalid in (0.74, 1.51):
        assert client.patch(f"/api/drafts/{draft_id}", json={"playback_rate": invalid}).status_code == 422
    assert client.patch(f"/api/drafts/{draft_id}", json={"playback_rate": None}).status_code == 422
    for invalid in (float("nan"), float("inf"), True, "1.2"):
        with pytest.raises(ValidationError):
            DraftPatchRequest.model_validate({"playback_rate": invalid})


def test_existing_draft_keeps_explicit_layout_positions(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    created = create_draft(client, project, candidate).json()
    explicit = {
        "video_area_position_y": 0.34,
        "title_position_y": 0.11,
        "subtitle_position_y": 0.25,
    }
    saved = client.patch(f"/api/drafts/{created['id']}", json=explicit)
    assert saved.status_code == 200
    loaded = create_draft(client, project, candidate).json()
    assert {key: loaded[key] for key in explicit} == explicit


def test_video_area_position_accepts_new_bounds_and_preserves_legacy_explicit_value(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate).json()["id"]
    for value in (0.22, 0.28, 0.34):
        response = client.patch(f"/api/drafts/{draft_id}", json={"video_area_position_y": value})
        assert response.status_code == 200
        assert response.json()["video_area_position_y"] == value
    for value in (0.219, 0.341):
        assert client.patch(f"/api/drafts/{draft_id}", json={"video_area_position_y": value}).status_code == 422

    draft = db_session.get(ClipDraft, draft_id)
    draft.video_area_position_y = 0.38
    db_session.commit()
    assert client.get(f"/api/drafts/{draft_id}").json()["video_area_position_y"] == 0.38
    unchanged = client.patch(
        f"/api/drafts/{draft_id}",
        json={"custom_title": "기존 위치 보존", "video_area_position_y": 0.38},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["video_area_position_y"] == 0.38
    assert client.patch(f"/api/drafts/{draft_id}", json={"video_area_position_y": 0.37}).status_code == 422


def test_title_sanitization_and_crop_validation(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate).json()["id"]
    cleaned = client.patch(f"/api/drafts/{draft_id}", json={"custom_title": "<b>안전한 제목</b>"})
    assert cleaned.json()["custom_title"] == "안전한 제목"
    assert client.patch(f"/api/drafts/{draft_id}", json={"crop_position_x": 1.1}).status_code == 422
    assert client.patch(f"/api/drafts/{draft_id}", json={"custom_title": "가" * 61}).status_code == 422


def test_visual_settings_save_validate_and_persist(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate, selected_title_order=1).json()["id"]
    settings = {
        "title_highlight_text": "믿음",
        "title_highlight_ranges": [{"start": 0, "end": 2}, {"start": 4, "end": 6}],
        "zoom_scale": 1.32,
        "crop_position_x": 0.42,
        "crop_position_y": 0.64,
        "video_area_position_y": 0.34,
        "video_area_height": 0.5,
        "title_font_scale": 1.2,
        "title_position_y": 0.14,
        "subtitle_font_scale": 0.9,
        "subtitle_position_y": 0.36,
        "template_type": "sermon_letterbox_v1",
    }
    response = client.patch(f"/api/drafts/{draft_id}", json=settings)
    assert response.status_code == 200
    loaded = client.get(f"/api/drafts/{draft_id}").json()
    for key, value in settings.items():
        assert loaded[key] == value

    invalid_values = {
        "zoom_scale": 1.41,
        "crop_position_x": -0.01,
        "crop_position_y": 1.01,
        "video_area_position_y": 0.219,
        "video_area_height": 0.59,
        "title_font_scale": 0.69,
        "title_position_y": 0.29,
        "subtitle_font_scale": 1.51,
        "subtitle_position_y": 0.51,
    }
    for field, value in invalid_values.items():
        rejected = client.patch(f"/api/drafts/{draft_id}", json={field: value})
        assert rejected.status_code == 422, field
    for removed_field in ("background_darkness", "subject_brightness", "subject_mask_enabled", "subject_mask_feather", "subject_mask_threshold"):
        rejected = client.patch(f"/api/drafts/{draft_id}", json={removed_field: 0})
        assert rejected.status_code == 422, removed_field


def test_title_highlight_ranges_normalize_validate_and_reset_with_title(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate).json()["id"]
    titled = client.patch(f"/api/drafts/{draft_id}", json={"custom_title": "자족은 무엇인가?"})
    assert titled.status_code == 200

    normalized = client.patch(f"/api/drafts/{draft_id}", json={
        "title_highlight_ranges": [
            {"start": 4, "end": 6}, {"start": 0, "end": 2},
            {"start": 1, "end": 3}, {"start": 0, "end": 2},
        ],
    })
    assert normalized.status_code == 200
    assert normalized.json()["title_highlight_ranges"] == [
        {"start": 0, "end": 3}, {"start": 4, "end": 6},
    ]

    whitespace = client.patch(f"/api/drafts/{draft_id}", json={"title_highlight_ranges": [{"start": 3, "end": 4}]})
    assert whitespace.status_code == 200
    assert whitespace.json()["title_highlight_ranges"] == []

    invalid_ranges = [
        [{"start": -1, "end": 2}], [{"start": 2, "end": 2}],
        [{"start": 0, "end": 99}], [{"start": 0.5, "end": 2}],
        [{"start": True, "end": 2}], [{"start": 0}],
    ]
    for ranges in invalid_ranges:
        assert client.patch(f"/api/drafts/{draft_id}", json={"title_highlight_ranges": ranges}).status_code == 422

    client.patch(f"/api/drafts/{draft_id}", json={"title_highlight_ranges": [{"start": 0, "end": 2}]})
    changed = client.patch(f"/api/drafts/{draft_id}", json={"custom_title": "제목 변경"})
    assert changed.status_code == 200
    assert changed.json()["title_highlight_ranges"] == []


def test_legacy_highlight_text_converts_only_its_first_occurrence(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate).json()["id"]
    client.patch(f"/api/drafts/{draft_id}", json={"custom_title": "믿음은 믿음을 낳는다"})
    converted = client.patch(f"/api/drafts/{draft_id}", json={"title_highlight_text": "믿음"})
    assert converted.status_code == 200
    assert converted.json()["title_highlight_ranges"] == [{"start": 0, "end": 2}]


def test_existing_clip_draft_receives_non_destructive_visual_defaults(tmp_path):
    database_path = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{database_path}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE clip_drafts (
                id INTEGER PRIMARY KEY,
                crop_position_x FLOAT NOT NULL DEFAULT 0.5,
                custom_title VARCHAR(500) NOT NULL DEFAULT '',
                title_highlight_text VARCHAR(500) NOT NULL DEFAULT '',
                zoom_scale FLOAT NOT NULL DEFAULT 1.35,
                subtitle_position_y FLOAT NOT NULL DEFAULT 0.31,
                subject_brightness FLOAT NOT NULL DEFAULT 1.0,
                subject_mask_feather FLOAT NOT NULL DEFAULT 0.12,
                subject_mask_threshold FLOAT NOT NULL DEFAULT 0.5,
                template_type VARCHAR(40) NOT NULL DEFAULT 'sermon_focus_v1'
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO clip_drafts (id, crop_position_x, custom_title, title_highlight_text, zoom_scale) VALUES (1, 0.25, '보존할 제목', '보존할', 1.8)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE draft_subtitles (id INTEGER PRIMARY KEY, draft_id INTEGER, edited_text TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO draft_subtitles (id, draft_id, edited_text) VALUES (1, 1, '보존할 실제 자막')"
        )
    _add_mvp_columns(legacy_engine)
    _add_mvp_columns(legacy_engine)
    columns = {column["name"] for column in inspect(legacy_engine).get_columns("clip_drafts")}
    assert {"title_highlight_ranges", "video_area_position_y", "video_area_height", "crop_position_y", "background_darkness", "subject_mask_enabled", "playback_rate", "template_type"} <= columns
    with legacy_engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM clip_drafts WHERE id = 1")).mappings().one()
        subtitle = connection.execute(text("SELECT edited_text FROM draft_subtitles WHERE id = 1")).scalar_one()
    assert row["crop_position_x"] == 0.25
    assert row["custom_title"] == "보존할 제목"
    assert json.loads(row["title_highlight_ranges"]) == [{"start": 0, "end": 3}]
    assert subtitle == "보존할 실제 자막"
    assert row["zoom_scale"] == 1.4
    assert row["crop_position_y"] == 0.6
    assert row["video_area_position_y"] == 0.30
    assert row["video_area_height"] == 0.48
    assert row["title_position_y"] == 0.08
    assert row["subtitle_position_y"] == 0.25
    assert row["playback_rate"] == 1.0
    assert row["subject_mask_enabled"] == 1
    assert row["template_type"] == "sermon_letterbox_v1"


def test_range_change_regenerates_subtitles_and_rejects_bad_ranges(client, db_session):
    project, candidate, segments = seed_draft_source(db_session)
    draft_id = create_draft(client, project, candidate).json()["id"]
    changed = client.patch(f"/api/drafts/{draft_id}/range", json={"start_segment_id": segments[2].id, "end_segment_id": segments[5].id, "regenerate_subtitles": True})
    assert changed.status_code == 200
    payload = changed.json()
    assert payload["range"]["start_sec"] == 20
    assert payload["range"]["end_sec"] == 60
    assert all(20 <= item["start_sec"] < item["end_sec"] <= 60 for item in payload["subtitles"])
    reversed_range = client.patch(f"/api/drafts/{draft_id}/range", json={"start_segment_id": segments[5].id, "end_segment_id": segments[2].id})
    assert reversed_range.status_code == 422
    missing = client.patch(f"/api/drafts/{draft_id}/range", json={"start_segment_id": 999999, "end_segment_id": segments[5].id})
    assert missing.status_code == 404
    other_project, _, other_segments = seed_draft_source(db_session)
    cross = client.patch(f"/api/drafts/{draft_id}/range", json={"start_segment_id": other_segments[0].id, "end_segment_id": other_segments[1].id})
    assert cross.status_code == 422


def test_subtitle_edit_preserves_original_and_reset_restores_source(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    created = create_draft(client, project, candidate).json()
    cue = created["subtitles"][0]
    edited = client.patch(f"/api/drafts/{created['id']}/subtitles/{cue['id']}", json={"edited_text": "사용자 편집 자막"})
    saved = next(item for item in edited.json()["subtitles"] if item["id"] == cue["id"])
    assert saved["original_text"] == cue["original_text"]
    assert saved["edited_text"] == "사용자 편집 자막"
    assert saved["is_edited"] is True
    reset = client.post(f"/api/drafts/{created['id']}/subtitles/reset").json()
    assert all(item["edited_text"] == item["original_text"] and not item["is_edited"] for item in reset["subtitles"])


def test_bulk_save_rejects_original_or_time_tampering(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    created = create_draft(client, project, candidate).json()
    items = [{key: item[key] for key in ("id", "cue_order", "start_sec", "end_sec", "edited_text")} for item in created["subtitles"]]
    items[0]["edited_text"] = "저장된 편집문"
    saved = client.put(f"/api/drafts/{created['id']}/subtitles", json={"subtitles": items})
    assert saved.status_code == 200
    assert saved.json()["subtitles"][0]["original_text"] == created["subtitles"][0]["original_text"]
    items[0]["start_sec"] = 0
    assert client.put(f"/api/drafts/{created['id']}/subtitles", json={"subtitles": items}).status_code == 422


def test_split_and_adjacent_merge(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    created = create_draft(client, project, candidate).json()
    first = created["subtitles"][0]
    split = client.post(f"/api/drafts/{created['id']}/subtitles/{first['id']}/split", json={"split_index": 6})
    assert split.status_code == 200
    split_items = split.json()["subtitles"]
    assert len(split_items) == len(created["subtitles"]) + 1
    assert split_items[0]["end_sec"] <= split_items[1]["start_sec"] + 0.01
    merged = client.post(f"/api/drafts/{created['id']}/subtitles/merge", json={"first_subtitle_id": split_items[0]["id"], "second_subtitle_id": split_items[1]["id"]})
    assert merged.status_code == 200
    assert len(merged.json()["subtitles"]) == len(created["subtitles"])
    current = merged.json()["subtitles"]
    non_adjacent = client.post(f"/api/drafts/{created['id']}/subtitles/merge", json={"first_subtitle_id": current[0]["id"], "second_subtitle_id": current[-1]["id"]})
    assert non_adjacent.status_code == 422


def test_draft_not_found_and_candidate_project_validation(client, db_session):
    project, candidate, _ = seed_draft_source(db_session)
    other_project, _, _ = seed_draft_source(db_session)
    assert client.get("/api/drafts/999999").status_code == 404
    assert create_draft(client, other_project, candidate).status_code == 404
    assert db_session.query(DraftSubtitle).count() == 0
