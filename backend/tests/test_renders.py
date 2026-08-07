import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.models import ClipCandidate, ClipDraft, DraftSubtitle, Project, RenderJob, TranscriptSegment
from app.services.render_crop import calculate_render_crop
from app.services.ffmpeg_filter_builder import build_ffmpeg_command
from app.services.render_assets import BannerAsset, calculate_banner_layout, get_template_banner, inspect_banner_asset
from app.services.render_service import (
    RenderError,
    create_render_job,
    process_render_job,
    recover_stalled_render_jobs,
    validate_rendered_file,
)
from app.services.subtitle_renderer import build_relative_cues, render_subtitle_timeline
from app.services.title_renderer import TITLE_LETTER_SPACING_EM, calculate_title_layout, render_title_png


def seed_renderable_draft(db_session, sample_video: Path, title: str = "믿음으로\n걸어갑시다") -> ClipDraft:
    project = Project(
        id="render-project", original_file_name="실제 설교.mp4", stored_file_path=str(sample_video),
        duration_seconds=3, width=320, height=180, file_size=sample_video.stat().st_size,
        status="completed", progress=100, analysis_mode="real",
    )
    segment = TranscriptSegment(
        project=project, start_sec=0.2, end_sec=1.4, text="실제 전사 자막입니다.", segment_order=1,
    )
    candidate = ClipCandidate(
        project=project, candidate_order=1, recommendation_type="핵심 메시지",
        start_segment_id=None, end_segment_id=None, segment_count=1,
        start_sec=0.2, end_sec=1.4, duration_sec=1.2, transcript=segment.text,
        main_topic="믿음", selection_reason="테스트", centrality_score=90, standalone_score=90,
        hook_score=90, emotional_score=90, overall_score=90,
    )
    db_session.add_all([project, segment, candidate])
    db_session.flush()
    candidate.start_segment_id = segment.id
    candidate.end_segment_id = segment.id
    draft = ClipDraft(
        project=project, candidate=candidate, start_segment_id=segment.id, end_segment_id=segment.id,
        start_sec=0.2, end_sec=1.4, duration_sec=1.2, custom_title=title,
        title_highlight_text="걸어갑시다", title_highlight_ranges='[{"start":5,"end":10}]',
        zoom_scale=1.12, crop_position_x=0.5, crop_position_y=0.5,
        video_area_position_y=0.34, video_area_height=0.48, title_font_scale=1,
        title_position_y=0.11, subtitle_font_scale=1, subtitle_position_y=0.25,
        template_type="sermon_letterbox_v1", status="ready",
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add(DraftSubtitle(
        draft=draft, cue_order=1, start_sec=0.2, end_sec=1.4,
        original_text="실제 전사 자막입니다.", edited_text="실제 전사 자막입니다.", is_edited=False,
    ))
    db_session.commit()
    return draft


def test_render_job_snapshot_duplicate_and_version(db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    first, created = create_render_job(db_session, draft.id)
    duplicate, duplicate_created = create_render_job(db_session, draft.id)
    assert created is True
    assert duplicate_created is False
    assert duplicate.id == first.id
    snapshot = json.loads(first.settings_snapshot)
    assert snapshot["custom_title"] == draft.custom_title
    assert snapshot["subtitles"][0]["edited_text"] == "실제 전사 자막입니다."
    assert snapshot["title_highlight_ranges"] == [{"start": 5, "end": 10}]
    assert snapshot["title_layout"]["font_size_px"] == 84
    assert [line["text"] for line in snapshot["title_layout"]["lines"]] == ["믿음으로", "걸어갑시다"]
    assert "video_darkness" not in snapshot
    assert snapshot["banner"]["asset_key"] == "onnuri_vision_church"
    assert snapshot["banner"]["width_ratio"] == 0.46
    assert snapshot["banner"]["position_x"] == 0.5
    assert snapshot["banner"]["position_y"] == 0.83
    assert snapshot["video_area_position_y"] == 0.34
    assert snapshot["title_position_y"] == 0.11
    assert snapshot["subtitle_position_y"] == 0.25
    assert snapshot["playback_rate"] == 1.0
    assert snapshot["output_duration_sec"] == pytest.approx(1.2)
    assert snapshot["fonts"]["title_key"] == "pretendard_black_v1"
    assert snapshot["fonts"]["title_name"] == "Pretendard Black"
    first.status = "completed"
    db_session.commit()
    second, second_created = create_render_job(db_session, draft.id)
    assert second_created is True
    assert second.version == 2
    assert json.loads(first.settings_snapshot)["custom_title"] == draft.custom_title


def test_render_snapshot_uses_new_letterbox_defaults(db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    draft.video_area_position_y = 0.30
    draft.title_position_y = 0.08
    draft.subtitle_position_y = 0.21
    db_session.commit()
    job, _ = create_render_job(db_session, draft.id)
    snapshot = json.loads(job.settings_snapshot)
    assert snapshot["video_area_position_y"] == 0.30
    assert snapshot["title_position_y"] == 0.08
    assert snapshot["subtitle_position_y"] == 0.21
    assert snapshot["banner"]["width_ratio"] == 0.46
    assert snapshot["banner"]["position_y"] == 0.83


def test_ffmpeg_command_does_not_apply_video_darkness(tmp_path):
    crop = calculate_render_crop(1920, 1080, 1080, 922, 1.12, 0.5, 0.5)
    command = build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        source_path=tmp_path / "source.mp4",
        overlay_manifest_path=tmp_path / "overlays.ffconcat",
        temporary_output=tmp_path / "output.mp4",
        start_sec=10,
        duration_sec=45,
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        crf=20,
        preset="medium",
        video_top=653,
        video_height=922,
        crop=crop,
    )
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "colorchannelmixer" not in filter_graph
    assert "brightness" not in filter_graph


def test_ffmpeg_command_applies_matching_video_and_audio_speed(tmp_path):
    crop = calculate_render_crop(1920, 1080, 1080, 922, 1.12, 0.5, 0.5)
    command = build_ffmpeg_command(
        ffmpeg_binary="ffmpeg", source_path=tmp_path / "source.mp4",
        overlay_manifest_path=tmp_path / "overlays.ffconcat",
        temporary_output=tmp_path / "output.mp4", start_sec=10,
        duration_sec=60, playback_rate=1.2, canvas_width=1080, canvas_height=1920, fps=30,
        crf=20, preset="medium", video_top=576, video_height=922, crop=crop,
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "setpts=(PTS-STARTPTS)/1.200000" in graph
    assert "d=50.000" in graph
    assert command[command.index("-af") + 1] == "atempo=1.200000,asetpts=PTS-STARTPTS"
    output_limit_index = command.index("-t", command.index("-af"))
    assert command[output_limit_index + 1] == "50.000"


def test_ffmpeg_command_uses_one_composited_overlay_timeline(tmp_path):
    crop = calculate_render_crop(1920, 1080, 1080, 922, 1.12, 0.5, 0.5)
    command = build_ffmpeg_command(
        ffmpeg_binary="ffmpeg", source_path=tmp_path / "source.mp4",
        overlay_manifest_path=tmp_path / "overlays.ffconcat",
        temporary_output=tmp_path / "output.mp4", start_sec=10,
        duration_sec=45, canvas_width=1080, canvas_height=1920, fps=30, crf=20,
        preset="medium", video_top=576, video_height=922, crop=crop,
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "[1:v]format=rgba" in graph
    assert command.count("-i") == 2
    assert command[command.index("-f") + 1] == "concat"
    assert command[command.index("-threads") + 1] == "1"


def test_concat_subtitle_timeline_contains_cues_and_gaps(tmp_path):
    settings = get_settings()
    title = tmp_path / "title.png"
    banner = get_template_banner("sermon_letterbox_v1").path
    from PIL import Image
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(title)
    output, assets = render_subtitle_timeline(
        tmp_path,
        [{"start_sec": 0.5, "end_sec": 2.25, "text": "실제 전사 자막"}],
        1080,
        1920,
        settings.subtitle_font_path,
        52,
        0.21,
        3.0,
        title,
        banner,
        497,
        100,
        292,
        1594,
    )
    contents = output.read_text(encoding="utf-8")
    assert "duration 0.500000" in contents
    assert "duration 1.750000" in contents
    assert "duration 0.750000" in contents
    assert "overlay_001.png" in contents
    assert all(path.is_file() for path in assets)


def test_pretendard_black_is_the_same_frontend_and_backend_asset():
    settings = get_settings()
    frontend_font = settings.title_font_path.parents[3] / "frontend" / "app" / "fonts" / "Pretendard-Black.otf"
    assert settings.title_font_name == "Pretendard Black"
    assert settings.title_font_path.name == "Pretendard-Black.otf"
    assert frontend_font.is_file()
    assert hashlib.sha256(settings.title_font_path.read_bytes()).digest() == hashlib.sha256(frontend_font.read_bytes()).digest()
    assert TITLE_LETTER_SPACING_EM == -0.03


def test_render_creation_rejects_missing_source_and_font(db_session, sample_video, tmp_path):
    draft = seed_renderable_draft(db_session, sample_video)
    draft.project.stored_file_path = str(tmp_path / "missing.mp4")
    db_session.commit()
    with pytest.raises(RenderError, match="원본 영상"):
        create_render_job(db_session, draft.id)
    draft.project.stored_file_path = str(sample_video)
    db_session.commit()
    settings = Settings(title_font_path=tmp_path / "missing.ttf")
    with pytest.raises(RenderError, match="제목 글꼴"):
        create_render_job(db_session, draft.id, settings)


def test_relative_subtitle_time_conversion_and_clipping():
    cues = [
        {"start_sec": 9.5, "end_sec": 11.0, "edited_text": "앞부분", "original_text": "원문"},
        {"start_sec": 14.0, "end_sec": 16.0, "edited_text": "", "original_text": "뒷부분"},
        {"start_sec": 20.0, "end_sec": 21.0, "edited_text": "제외", "original_text": "제외"},
    ]
    relative = build_relative_cues(cues, 10.0, 15.0)
    assert relative == [
        {"start_sec": 0.0, "end_sec": 1.0, "text": "앞부분"},
        {"start_sec": 4.0, "end_sec": 5.0, "text": "뒷부분"},
    ]
    faster = build_relative_cues(cues, 10.0, 15.0, 1.2)
    assert faster == [
        {"start_sec": 0.0, "end_sec": pytest.approx(1 / 1.2), "text": "앞부분"},
        {"start_sec": pytest.approx(4 / 1.2), "end_sec": pytest.approx(5 / 1.2), "text": "뒷부분"},
    ]


def test_banner_asset_alpha_and_safe_centered_layout(tmp_path):
    from PIL import Image

    asset = get_template_banner("sermon_letterbox_v1")
    source_width, source_height = inspect_banner_asset(asset)
    layout = calculate_banner_layout(1080, 1920, source_width, source_height, 0.46, 0.5, 0.83)
    with Image.open(asset.path) as image:
        alpha_min, alpha_max = image.getchannel("A").getextrema()
    assert (source_width, source_height) == (1799, 361)
    assert (alpha_min, alpha_max) == (0, 255)
    assert (layout.width, layout.height, layout.x, layout.y) == (497, 100, 292, 1594)
    assert abs((layout.x + layout.width / 2) - 540) <= 0.5
    assert layout.y > round(1920 * (0.34 + 0.48))
    assert layout.bottom <= 1760
    assert 1920 - layout.bottom >= 160
    missing = BannerAsset(True, "missing", tmp_path / "missing.png", 0.58, 0.5, 0.86)
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        inspect_banner_asset(missing)


@pytest.mark.parametrize("source", [(1920, 1080), (1280, 720), (1080, 1920)])
@pytest.mark.parametrize("zoom", [1.0, 1.4])
@pytest.mark.parametrize("position", [0.0, 0.5, 1.0])
def test_crop_fills_target_and_stays_inside_source(source, zoom, position):
    crop = calculate_render_crop(*source, 1080, 922, zoom, position, position)
    assert 0 <= crop.crop_x <= source[0] - crop.crop_width + 0.001
    assert 0 <= crop.crop_y <= source[1] - crop.crop_height + 0.001
    assert crop.crop_width * crop.scale >= 1080 - 0.001
    assert crop.crop_height * crop.scale >= 922 - 0.001


def test_title_renderer_supports_empty_and_missing_highlight(tmp_path):
    settings = get_settings()
    empty = tmp_path / "empty.png"
    highlighted = tmp_path / "highlighted.png"
    render_title_png(empty, "", [], settings.title_font_path, 1080, 1920, 1, 0.11)
    render_title_png(highlighted, "실제 제목", [], settings.title_font_path, 1080, 1920, 1, 0.11)
    assert empty.stat().st_size > 0
    assert highlighted.stat().st_size > 0


def test_title_renderer_never_blocks_generation_for_long_or_multiline_titles(tmp_path):
    settings = get_settings()
    cases = [
        "첫 번째 줄입니다\n두 번째 줄입니다\n세 번째 줄도 그대로 생성합니다",
        "공백없이아주긴제목도렌더링실패없이자동으로줄을나누어끝까지쇼츠를생성해야합니다" * 2,
    ]
    for index, title in enumerate(cases):
        output = tmp_path / f"long-title-{index}.png"
        render_title_png(output, title[:60], [], settings.title_font_path, 1080, 1920, 1.5, 0.11)
        assert output.is_file()
        assert output.stat().st_size > 0


@pytest.mark.parametrize(
    ("title", "expected_lines", "expected_size", "auto_fit"),
    [
        ("믿음이란 무엇인가?", ["믿음이란 무엇인가?"], 84, False),
        ("우리가 하나님을\n바라봐야 하는 이유", ["우리가 하나님을", "바라봐야 하는 이유"], 84, False),
        (
            "자족하려면 눈높이를 낮추라고요?\n큰 오해입니다",
            ["자족하려면 눈높이를", "낮추라고요?", "큰 오해입니다"],
            84,
            False,
        ),
        ("첫째 줄\n둘째 줄\n셋째 줄", ["첫째 줄", "둘째 줄", "셋째 줄"], 84, False),
    ],
)
def test_canonical_title_layout_preserves_preview_lines(title, expected_lines, expected_size, auto_fit):
    settings = get_settings()
    layout = calculate_title_layout(title, settings.title_font_path, 1080, 1920, 1, 0.11)
    assert [line.text for line in layout.lines] == expected_lines
    assert layout.font_size_px == expected_size
    assert layout.line_height_px == 91
    assert (layout.area.x, layout.area.y, layout.area.width, layout.area.height) == (76, 211, 929, 442)
    assert layout.auto_fit_applied is auto_fit


def test_canonical_title_layout_char_wraps_without_failing():
    settings = get_settings()
    title = "공백없이아주긴제목도렌더링실패없이자동으로줄을나누어끝까지쇼츠를생성해야합니다"
    layout = calculate_title_layout(title, settings.title_font_path, 1080, 1920, 1, 0.11)
    assert "".join(line.text for line in layout.lines) == title
    assert layout.font_size_px == 36
    assert layout.character_wrap_applied is True
    assert layout.auto_fit_applied is True
    assert all(line.width_px <= layout.area.width for line in layout.lines)


def test_title_layout_preview_api_returns_the_exact_canonical_image(client):
    title = "자족하려면 눈높이를 낮추라고요?\n큰 오해입니다"
    response = client.post("/api/title-layout/preview", json={
        "title": title,
        "title_font_scale": 1,
        "title_position_y": 0.11,
        "title_highlight_ranges": [{"start": 0, "end": 5}, {"start": 18, "end": 20}],
    })
    assert response.status_code == 200
    payload = response.json()
    assert [line["text"] for line in payload["lines"]] == [
        "자족하려면 눈높이를", "낮추라고요?", "큰 오해입니다",
    ]
    assert payload["font_size_px"] == 84
    assert payload["line_height_px"] == 91
    assert payload["auto_fit_applied"] is False
    assert payload["font_key"] == "pretendard_black_v1"
    assert payload["font_name"] == "Pretendard Black"
    assert payload["image_data_url"].startswith("data:image/png;base64,")


def test_title_renderer_colors_only_existing_highlight(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    settings = get_settings()
    cases = [
        ("자족은 무엇인가?", [{"start": 0, "end": 2}, {"start": 4, "end": 6}], [("자족", True), ("은 ", False), ("무엇", True), ("인가?", False)]),
        ("믿음은 믿음을 낳는다", [{"start": 4, "end": 6}], [("믿음은 ", False), ("믿음", True), ("을 낳는다", False)]),
    ]
    font = ImageFont.truetype(str(settings.title_font_path), size=84)
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for index, (title, ranges, expected_parts) in enumerate(cases):
        output = tmp_path / f"title-{index}.png"
        render_title_png(output, title, ranges, settings.title_font_path, 1080, 1920, 1, 0.11)
        with Image.open(output).convert("RGBA") as rendered:
            cursor = (1080 - measure.textlength(title, font=font)) / 2
            for part, highlighted in expected_parts:
                part_width = measure.textlength(part, font=font)
                region = rendered.crop((int(cursor), 205, int(cursor + part_width + 1), 310))
                target = (255, 216, 77) if highlighted else (255, 255, 255)
                assert sum(1 for pixel in region.getdata() if pixel[:3] == target and pixel[3] > 0) > 10
                cursor += part_width


def test_render_start_and_list_api(monkeypatch, client, db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    monkeypatch.setattr("app.api.renders.run_render_job", lambda render_id: None)
    created = client.post(f"/api/drafts/{draft.id}/renders")
    duplicate = client.post(f"/api/drafts/{draft.id}/renders")
    listed = client.get(f"/api/drafts/{draft.id}/renders")
    assert created.status_code == 202
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == created.json()["id"]
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]


def test_render_creation_rejects_invalid_range(db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    draft.end_sec = 4
    draft.duration_sec = 3.8
    db_session.commit()
    with pytest.raises(RenderError, match="영상 구간"):
        create_render_job(db_session, draft.id)


def test_existing_snapshot_without_playback_rate_renders_as_1x(db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    job, _ = create_render_job(db_session, draft.id)
    snapshot = json.loads(job.settings_snapshot)
    snapshot.pop("playback_rate")
    snapshot.pop("output_duration_sec")
    job.settings_snapshot = json.dumps(snapshot, ensure_ascii=False)
    db_session.commit()
    process_render_job(db_session, job.id)
    db_session.refresh(job)
    assert job.status == "completed"
    assert job.output_duration_sec == pytest.approx(1.2, abs=0.1)


def test_real_ffmpeg_render_stream_range_and_download(client, db_session, sample_video, tmp_path):
    from PIL import Image

    draft = seed_renderable_draft(db_session, sample_video)
    draft.custom_title = "자족은 무엇인가?"
    draft.title_highlight_ranges = '[{"start":0,"end":2},{"start":4,"end":6}]'
    draft.video_area_position_y = 0.30
    draft.title_position_y = 0.08
    draft.subtitle_position_y = 0.21
    db_session.commit()
    job, _ = create_render_job(db_session, draft.id)
    process_render_job(db_session, job.id)
    db_session.refresh(job)
    assert job.status == "completed", job.error_message
    assert job.progress == 100
    assert job.output_width == 1080
    assert job.output_height == 1920
    rendered_frame = tmp_path / "rendered-frame.png"
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "0.6", "-i", job.output_file_path,
        "-frames:v", "1", str(rendered_frame),
    ], check=True)
    banner_source = inspect_banner_asset(get_template_banner("sermon_letterbox_v1"))
    layout = calculate_banner_layout(1080, 1920, *banner_source, 0.46, 0.5, 0.83)
    with Image.open(rendered_frame).convert("RGB") as frame:
        banner_region = frame.crop((layout.x, layout.y, layout.right, layout.bottom))
        non_black = sum(1 for pixel in banner_region.getdata() if max(pixel) > 30)
        transparent_corner = frame.getpixel((layout.right - 5, layout.y + 5))
        title_region = frame.crop((0, 130, 1080, 310))
        yellow_title_pixels = sum(1 for red, green, blue in title_region.getdata() if red > 150 and green > 120 and blue < 130)
        white_title_pixels = sum(1 for red, green, blue in title_region.getdata() if min(red, green, blue) > 160)
    assert non_black > 1_000
    assert max(transparent_corner) < 10
    assert yellow_title_pixels > 100
    assert white_title_pixels > 100
    full = client.get(f"/api/renders/{job.id}/video")
    partial = client.get(f"/api/renders/{job.id}/video", headers={"Range": "bytes=0-99"})
    download = client.get(f"/api/renders/{job.id}/download")
    assert full.status_code == 200 and full.headers["content-type"].startswith("video/mp4")
    assert partial.status_code == 206 and len(partial.content) == 100
    assert partial.headers["content-range"].startswith("bytes 0-99/")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]


def test_stream_rejects_output_path_outside_processed(client, db_session, sample_video, tmp_path):
    draft = seed_renderable_draft(db_session, sample_video)
    outside = tmp_path.parent / "outside-render.mp4"
    outside.write_bytes(b"video")
    job = RenderJob(
        project_id=draft.project_id, draft_id=draft.id, version=1, status="completed", progress=100,
        current_step="finalizing", output_file_path=str(outside), output_file_name="outside.mp4",
        output_file_size=5, output_duration_sec=1.2, output_width=1080, output_height=1920,
        settings_snapshot="{}", completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.commit()
    assert client.get(f"/api/renders/{job.id}/video").status_code == 404


def test_ffmpeg_failure_marks_job_failed(monkeypatch, db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    job, _ = create_render_job(db_session, draft.id)

    class FailedProcess:
        stdout = iter(())

        def wait(self):
            return 1

    monkeypatch.setattr("app.services.render_service.subprocess.Popen", lambda *args, **kwargs: FailedProcess())
    process_render_job(db_session, job.id)
    db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "ffmpeg_failed"
    assert job.output_file_path is None


def test_ffprobe_validation_failure(monkeypatch, tmp_path):
    output = tmp_path / "bad.mp4"
    output.write_bytes(b"not-an-mp4")
    monkeypatch.setattr("app.services.render_service._probe", lambda path: {"streams": [], "format": {"duration": "1"}})
    with pytest.raises(RenderError, match="영상 또는 오디오"):
        validate_rendered_file(output, 1, 1080, 1920)


def test_recover_stalled_jobs(db_session, sample_video):
    draft = seed_renderable_draft(db_session, sample_video)
    job, _ = create_render_job(db_session, draft.id)
    job.status = "rendering"
    job.started_at = datetime.now(timezone.utc)
    db_session.commit()
    assert recover_stalled_render_jobs(db_session) == 1
    db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "server_restart"
