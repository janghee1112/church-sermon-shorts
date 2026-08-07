import json
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.database.session import SessionLocal
from app.models import ClipDraft, RenderJob
from app.services.ffmpeg_filter_builder import build_ffmpeg_command
from app.services.render_crop import calculate_render_crop
from app.services.render_assets import calculate_banner_layout, get_template_banner, inspect_banner_asset
from app.services.render_file_service import safe_download_name
from app.services.subtitle_renderer import build_relative_cues, render_subtitle_images
from app.services.title_renderer import (
    TitleLayout,
    TitleRenderError,
    calculate_title_layout,
    render_title_png,
)
from app.services.title_highlight import legacy_highlight_range, load_highlight_ranges


logger = logging.getLogger(__name__)
ACTIVE_RENDER_STATUSES = ("queued", "preparing", "rendering")


class RenderError(Exception):
    def __init__(self, message: str, code: str = "render_failed") -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_render(db: Session, render_id: int) -> RenderJob:
    job = db.get(RenderJob, render_id)
    if job is None:
        raise RenderError("렌더링 작업을 찾을 수 없습니다.", "render_not_found")
    return job


def list_renders(db: Session, draft_id: int, limit: int = 5) -> list[RenderJob]:
    if db.get(ClipDraft, draft_id) is None:
        raise RenderError("편집 초안을 찾을 수 없습니다.", "draft_not_found")
    return list(
        db.scalars(
            select(RenderJob)
            .where(RenderJob.draft_id == draft_id)
            .order_by(RenderJob.version.desc())
            .limit(max(1, min(limit, 20)))
        ).all()
    )


def _source_path(draft: ClipDraft) -> Path:
    path = Path(draft.project.stored_file_path)
    return path if path.is_absolute() else path.resolve()


def _verify_render_dependencies(draft: ClipDraft, settings: Settings) -> None:
    source = _source_path(draft)
    if not source.is_file():
        raise RenderError("원본 영상 파일을 찾을 수 없습니다.", "source_missing")
    if draft.start_sec < 0 or draft.end_sec <= draft.start_sec or draft.end_sec > draft.project.duration_seconds + 0.05:
        raise RenderError("선택한 영상 구간이 올바르지 않습니다.", "invalid_range")
    if not draft.subtitles:
        raise RenderError("렌더링할 자막이 없습니다.", "subtitles_missing")
    if not 0.75 <= draft.playback_rate <= 1.5:
        raise RenderError("재생 속도가 올바르지 않습니다.", "invalid_playback_rate")
    for cue in draft.subtitles:
        if cue.end_sec <= cue.start_sec or cue.start_sec < draft.start_sec - 0.01 or cue.end_sec > draft.end_sec + 0.01:
            raise RenderError("자막 시간 정보가 올바르지 않습니다.", "invalid_subtitle_time")
    if not settings.title_font_path.is_file():
        raise RenderError("렌더링에 사용할 제목 글꼴을 찾을 수 없습니다.", "title_font_missing")
    if not settings.subtitle_font_path.is_file():
        raise RenderError("렌더링에 사용할 자막 글꼴을 찾을 수 없습니다.", "subtitle_font_missing")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RenderError("영상 생성 도구를 찾을 수 없습니다.", "ffmpeg_missing")
    try:
        inspect_banner_asset(get_template_banner(draft.template_type))
    except ValueError as exc:
        raise RenderError(str(exc), "banner_asset_invalid") from exc


def _build_snapshot(draft: ClipDraft, settings: Settings) -> dict[str, Any]:
    banner = get_template_banner(draft.template_type)
    title_layout = calculate_title_layout(
        draft.custom_title,
        settings.title_font_path,
        settings.render_width,
        settings.render_height,
        draft.title_font_scale,
        draft.title_position_y,
    )
    return {
        "start_sec": draft.start_sec,
        "end_sec": draft.end_sec,
        "duration_sec": draft.end_sec - draft.start_sec,
        "playback_rate": draft.playback_rate,
        "output_duration_sec": (draft.end_sec - draft.start_sec) / draft.playback_rate,
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
        "title_layout": title_layout.to_dict(),
        "subtitle_font_scale": draft.subtitle_font_scale,
        "subtitle_position_y": draft.subtitle_position_y,
        "template_type": draft.template_type,
        "banner": {
            "enabled": banner.enabled,
            "asset_key": banner.asset_key,
            "asset_path": str(banner.path),
            "width_ratio": banner.width_ratio,
            "position_x": banner.position_x,
            "position_y": banner.position_y,
        },
        "subtitles": [
            {
                "id": cue.id,
                "cue_order": cue.cue_order,
                "start_sec": cue.start_sec,
                "end_sec": cue.end_sec,
                "original_text": cue.original_text,
                "edited_text": cue.edited_text,
            }
            for cue in sorted(draft.subtitles, key=lambda value: value.cue_order)
        ],
        "source": {
            "project_id": draft.project_id,
            "stored_file_path": str(_source_path(draft)),
            "original_file_name": draft.project.original_file_name,
            "width": draft.project.width,
            "height": draft.project.height,
            "duration_sec": draft.project.duration_seconds,
        },
        "fonts": {
            "title_key": "pretendard_black_v1",
            "subtitle_key": "myeongjo",
            "title_path": str(settings.title_font_path),
            "subtitle_path": str(settings.subtitle_font_path),
            "title_name": settings.title_font_name,
            "subtitle_name": settings.subtitle_font_name,
        },
        "output": {
            "width": settings.render_width,
            "height": settings.render_height,
            "fps": settings.render_fps,
            "crf": settings.render_crf,
            "preset": settings.render_preset,
            "video_codec": "libx264",
            "audio_codec": "aac",
            "pixel_format": "yuv420p",
        },
    }


def create_render_job(db: Session, draft_id: int, settings: Optional[Settings] = None) -> tuple[RenderJob, bool]:
    active = db.scalar(
        select(RenderJob)
        .where(RenderJob.draft_id == draft_id, RenderJob.status.in_(ACTIVE_RENDER_STATUSES))
        .order_by(RenderJob.version.desc())
    )
    if active is not None:
        return active, False
    draft = db.scalar(
        select(ClipDraft)
        .where(ClipDraft.id == draft_id)
        .options(selectinload(ClipDraft.project), selectinload(ClipDraft.subtitles))
    )
    if draft is None:
        raise RenderError("편집 초안을 찾을 수 없습니다.", "draft_not_found")
    render_settings = settings or get_settings()
    _verify_render_dependencies(draft, render_settings)
    version = (db.scalar(select(func.max(RenderJob.version)).where(RenderJob.draft_id == draft.id)) or 0) + 1
    try:
        snapshot = _build_snapshot(draft, render_settings)
    except TitleRenderError as exc:
        raise RenderError(str(exc), "title_layout_invalid") from exc
    job = RenderJob(
        project_id=draft.project_id,
        draft_id=draft.id,
        version=version,
        status="queued",
        progress=0,
        current_step="validating",
        settings_snapshot=json.dumps(snapshot, ensure_ascii=False),
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(RenderJob)
            .where(RenderJob.draft_id == draft_id, RenderJob.status.in_(ACTIVE_RENDER_STATUSES))
            .order_by(RenderJob.version.desc())
        )
        if concurrent is not None:
            return concurrent, False
        raise RenderError("렌더링 버전을 생성하지 못했습니다. 다시 시도해 주세요.", "render_version_conflict")
    db.refresh(job)
    return job, True


def serialize_render(job: RenderJob) -> dict[str, Any]:
    completed = job.status == "completed" and bool(job.output_file_path)
    return {
        "id": job.id,
        "project_id": job.project_id,
        "draft_id": job.draft_id,
        "version": job.version,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "output_file_name": job.output_file_name,
        "output_file_size": job.output_file_size,
        "output_duration_sec": job.output_duration_sec,
        "output_width": job.output_width,
        "output_height": job.output_height,
        "preview_url": f"/api/renders/{job.id}/video" if completed else None,
        "download_url": f"/api/renders/{job.id}/download" if completed else None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "updated_at": job.updated_at,
    }


def _set_state(db: Session, job: RenderJob, status: str, progress: int, step: str) -> None:
    job.status = status
    job.progress = max(job.progress, min(100, progress))
    job.current_step = step
    job.updated_at = _utc_now()
    db.commit()


def _probe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height", "-of", "json", str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RenderError("생성된 영상 파일 검증에 실패했습니다.", "ffprobe_failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RenderError("생성된 영상 파일 검증에 실패했습니다.", "ffprobe_invalid_json") from exc


def validate_rendered_file(path: Path, expected_duration: float, width: int, height: int) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RenderError("생성된 영상 파일 검증에 실패했습니다.", "output_missing")
    probe = _probe(path)
    streams = probe.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise RenderError("생성된 영상에 영상 또는 오디오가 없습니다.", "output_stream_missing")
    if int(video.get("width", 0)) != width or int(video.get("height", 0)) != height:
        raise RenderError("생성된 영상 해상도가 올바르지 않습니다.", "output_resolution_invalid")
    duration = float(probe.get("format", {}).get("duration", 0))
    if abs(duration - expected_duration) > 0.8:
        raise RenderError("생성된 영상 길이가 선택 구간과 일치하지 않습니다.", "output_duration_invalid")
    return {"duration": duration, "width": width, "height": height, "size": path.stat().st_size}


def _update_encoding_progress(db: Session, job: RenderJob, line: str, duration: float) -> None:
    if not line.startswith(("out_time_us=", "out_time_ms=")):
        return
    try:
        processed = int(line.split("=", 1)[1]) / 1_000_000
    except ValueError:
        return
    progress = 30 + round(min(1.0, processed / max(0.1, duration)) * 65)
    if progress >= job.progress + 1:
        job.progress = min(95, progress)
        job.updated_at = _utc_now()
        db.commit()


def process_render_job(db: Session, render_id: int) -> None:
    job: Optional[RenderJob] = None
    step = "validating"
    temporary_output: Optional[Path] = None
    try:
        job = get_render(db, render_id)
        if job.status != "queued":
            return
        snapshot = json.loads(job.settings_snapshot)
        job.started_at = _utc_now()
        _set_state(db, job, "preparing", 5, "validating")
        source_path = Path(snapshot["source"]["stored_file_path"])
        title_font = Path(snapshot["fonts"]["title_path"])
        subtitle_font = Path(snapshot["fonts"]["subtitle_path"])
        banner_path = Path(snapshot["banner"]["asset_path"])
        for path, message, code in (
            (source_path, "원본 영상 파일을 찾을 수 없습니다.", "source_missing"),
            (title_font, "렌더링에 사용할 제목 글꼴을 찾을 수 없습니다.", "title_font_missing"),
            (subtitle_font, "렌더링에 사용할 자막 글꼴을 찾을 수 없습니다.", "subtitle_font_missing"),
            (banner_path, "교회 배너 이미지 파일을 찾을 수 없습니다.", "banner_asset_invalid"),
        ):
            if not path.is_file():
                raise RenderError(message, code)

        step = "preparing_assets"
        _set_state(db, job, "preparing", 10, step)
        settings = get_settings()
        work_dir = settings.processed_dir / job.project_id / "renders" / str(job.id)
        work_dir.mkdir(parents=True, exist_ok=True)
        title_path = work_dir / "title.png"
        log_path = work_dir / "ffmpeg.log"
        temporary_output = work_dir / "output.tmp.mp4"
        output_name = f"short_{job.draft_id}_v{job.version}_{uuid.uuid4().hex[:12]}.mp4"
        final_output = work_dir / output_name
        output = snapshot["output"]
        playback_rate = float(snapshot.get("playback_rate", 1.0))
        if not 0.75 <= playback_rate <= 1.5:
            raise RenderError("재생 속도가 올바르지 않습니다.", "invalid_playback_rate")
        output_duration = float(snapshot.get("output_duration_sec", float(snapshot["duration_sec"]) / playback_rate))
        width = int(output["width"])
        height = int(output["height"])
        highlight_ranges = (
            snapshot["title_highlight_ranges"]
            if "title_highlight_ranges" in snapshot
            else legacy_highlight_range(
                str(snapshot["custom_title"]),
                str(snapshot.get("title_highlight_text", "")),
            )
        )
        stored_title_layout = snapshot.get("title_layout")
        render_title_png(
            title_path,
            str(snapshot["custom_title"]),
            highlight_ranges,
            title_font,
            width,
            height,
            float(snapshot["title_font_scale"]),
            float(snapshot["title_position_y"]),
            layout=TitleLayout.from_dict(stored_title_layout) if stored_title_layout else None,
        )
        relative_cues = build_relative_cues(
            snapshot["subtitles"], float(snapshot["start_sec"]), float(snapshot["end_sec"]), playback_rate,
        )
        if not relative_cues:
            raise RenderError("렌더링할 유효한 자막이 없습니다.", "subtitles_missing")
        subtitle_size = round(52 * min(1.5, max(0.7, float(snapshot["subtitle_font_scale"]))))
        subtitle_images = render_subtitle_images(
            work_dir, relative_cues, width, height, subtitle_font,
            subtitle_size, float(snapshot["subtitle_position_y"]),
        )

        step = "composing_video"
        _set_state(db, job, "preparing", 20, step)
        video_top = round(float(snapshot["video_area_position_y"]) * height)
        video_height = max(2, round(float(snapshot["video_area_height"]) * height / 2) * 2)
        if video_top < 0 or video_top + video_height > height:
            raise RenderError("영상 영역 위치가 캔버스를 벗어납니다.", "video_area_invalid")
        crop = calculate_render_crop(
            int(snapshot["source"]["width"]), int(snapshot["source"]["height"]), width, video_height,
            float(snapshot["zoom_scale"]), float(snapshot["crop_position_x"]), float(snapshot["crop_position_y"]),
        )
        try:
            banner_source_width, banner_source_height = inspect_banner_asset(
                get_template_banner(str(snapshot["template_type"]))
            )
            banner_layout = calculate_banner_layout(
                width, height, banner_source_width, banner_source_height,
                float(snapshot["banner"]["width_ratio"]),
                float(snapshot["banner"]["position_x"]),
                float(snapshot["banner"]["position_y"]),
            )
        except ValueError as exc:
            raise RenderError(str(exc), "banner_layout_invalid") from exc
        if banner_layout.y < video_top + video_height:
            raise RenderError("교회 배너가 영상 영역과 겹칩니다.", "banner_layout_invalid")
        command = build_ffmpeg_command(
            ffmpeg_binary="ffmpeg", source_path=source_path, title_path=title_path,
            subtitle_images=subtitle_images, banner_path=banner_path,
            banner_width=banner_layout.width, banner_height=banner_layout.height,
            banner_x=banner_layout.x, banner_y=banner_layout.y,
            temporary_output=temporary_output,
            start_sec=float(snapshot["start_sec"]), duration_sec=float(snapshot["duration_sec"]), playback_rate=playback_rate,
            canvas_width=width, canvas_height=height, fps=int(output["fps"]), crf=int(output["crf"]),
            preset=str(output["preset"]), video_top=video_top, video_height=video_height, crop=crop,
        )
        step = "encoding"
        _set_state(db, job, "rendering", 30, step)
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log_file, text=True)
            assert process.stdout is not None
            for progress_line in process.stdout:
                _update_encoding_progress(db, job, progress_line.strip(), output_duration)
            return_code = process.wait()
        if return_code != 0:
            try:
                ffmpeg_error = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                ffmpeg_error = "FFmpeg 로그를 읽을 수 없습니다."
            logger.error(
                "render_id=%s ffmpeg exited with code=%s: %s",
                render_id,
                return_code,
                ffmpeg_error,
            )
            raise RenderError("쇼츠 영상 생성에 실패했습니다.", "ffmpeg_failed")

        step = "finalizing"
        _set_state(db, job, "rendering", 96, step)
        metadata = validate_rendered_file(temporary_output, output_duration, width, height)
        os.replace(temporary_output, final_output)
        title_path.unlink(missing_ok=True)
        for subtitle_image, _, _ in subtitle_images:
            subtitle_image.unlink(missing_ok=True)
        log_path.unlink(missing_ok=True)
        job.status = "completed"
        job.progress = 100
        job.current_step = "finalizing"
        job.output_file_path = str(final_output)
        job.output_file_name = output_name
        job.output_file_size = metadata["size"]
        job.output_duration_sec = metadata["duration"]
        job.output_width = metadata["width"]
        job.output_height = metadata["height"]
        job.completed_at = _utc_now()
        job.updated_at = _utc_now()
        db.commit()
    except (RenderError, TitleRenderError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        if temporary_output is not None:
            temporary_output.unlink(missing_ok=True)
        if job is not None:
            job.status = "failed"
            job.current_step = step
            job.error_code = exc.code if isinstance(exc, RenderError) else "render_failed"
            job.error_message = str(exc) if isinstance(exc, (RenderError, TitleRenderError)) else "쇼츠 영상 생성에 실패했습니다."
            job.completed_at = _utc_now()
            job.updated_at = _utc_now()
            db.commit()
            logger.exception("render_id=%s step=%s failed", render_id, step)
    except Exception:
        if temporary_output is not None:
            temporary_output.unlink(missing_ok=True)
        if job is not None:
            job.status = "failed"
            job.current_step = step
            job.error_code = "unexpected_render_error"
            job.error_message = "쇼츠 영상 생성에 실패했습니다."
            job.completed_at = _utc_now()
            job.updated_at = _utc_now()
            db.commit()
        logger.exception("render_id=%s step=%s unexpected failure", render_id, step)


def run_render_job(render_id: int) -> None:
    db = SessionLocal()
    try:
        process_render_job(db, render_id)
    finally:
        db.close()


def recover_stalled_render_jobs(db: Session) -> int:
    jobs = db.scalars(select(RenderJob).where(RenderJob.status.in_(ACTIVE_RENDER_STATUSES))).all()
    for job in jobs:
        job.status = "failed"
        job.current_step = "finalizing"
        job.error_code = "server_restart"
        job.error_message = "서버가 재시작되어 쇼츠 생성이 중단되었습니다. 다시 시도해 주세요."
        job.completed_at = _utc_now()
        job.updated_at = _utc_now()
    db.commit()
    return len(jobs)


def download_name_for_job(job: RenderJob) -> str:
    try:
        title = str(json.loads(job.settings_snapshot).get("custom_title", ""))
    except json.JSONDecodeError:
        title = ""
    return safe_download_name(title, job.version)
