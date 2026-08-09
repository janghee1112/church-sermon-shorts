import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import Project, RenderJob


logger = logging.getLogger(__name__)
ACTIVE_ANALYSIS_STATUSES = {"extracting_audio", "transcribing", "analyzing"}
ACTIVE_RENDER_STATUSES = {"queued", "preparing", "rendering"}


class ProjectCleanupError(Exception):
    pass


@dataclass(frozen=True)
class CleanupResult:
    project_id: str
    deleted_files: int
    freed_bytes: int


@dataclass(frozen=True)
class _StagedPath:
    original: Path
    staged: Path
    file_count: int
    byte_count: int


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return path != root
    except ValueError:
        return False


def _managed_path(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve(strict=False)
    if not _is_inside(resolved_path, resolved_root):
        raise ProjectCleanupError("프로젝트 파일 경로를 안전하게 확인하지 못했습니다.")
    return resolved_path


def _path_usage(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return 1, path.stat().st_size
    file_count = 0
    byte_count = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            file_count += 1
            byte_count += item.stat().st_size
    return file_count, byte_count


def collect_project_paths(project: Project, settings: Settings) -> list[Path]:
    upload_path = _managed_path(Path(project.stored_file_path), settings.upload_dir)
    processed_path = _managed_path(settings.processed_dir / project.id, settings.processed_dir)
    paths = [upload_path, processed_path]
    for render in project.renders:
        if not render.output_file_path:
            continue
        output_path = _managed_path(Path(render.output_file_path), settings.processed_dir)
        if output_path != processed_path and processed_path not in output_path.parents:
            paths.append(output_path)
    return list(dict.fromkeys(paths))


def cleanup_project(db: Session, project: Project, settings: Settings | None = None) -> CleanupResult:
    cleanup_settings = settings or get_settings()
    if project.status in ACTIVE_ANALYSIS_STATUSES:
        raise ProjectCleanupError("현재 영상 분석이 진행 중입니다. 완료 또는 실패 후 다시 시도해 주세요.")
    active_render = db.scalar(
        select(RenderJob.id).where(
            RenderJob.project_id == project.id,
            RenderJob.status.in_(ACTIVE_RENDER_STATUSES),
        ).limit(1)
    )
    if active_render is not None:
        raise ProjectCleanupError("현재 쇼츠 영상 생성이 진행 중입니다. 완료 또는 실패 후 다시 시도해 주세요.")

    targets = collect_project_paths(project, cleanup_settings)
    staging_root = _managed_path(
        cleanup_settings.processed_dir / ".cleanup" / f"{project.id}-{uuid4().hex}",
        cleanup_settings.processed_dir,
    )
    staged: list[_StagedPath] = []
    try:
        for index, target in enumerate(targets):
            if not target.exists():
                continue
            file_count, byte_count = _path_usage(target)
            staging_root.mkdir(parents=True, exist_ok=True)
            staged_path = staging_root / f"{index}-{target.name}"
            os.replace(target, staged_path)
            staged.append(_StagedPath(target, staged_path, file_count, byte_count))
    except OSError as exc:
        for item in reversed(staged):
            item.original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item.staged, item.original)
        shutil.rmtree(staging_root, ignore_errors=True)
        raise ProjectCleanupError("프로젝트 파일을 정리하지 못했습니다. 다시 시도해 주세요.") from exc

    try:
        db.delete(project)
        db.commit()
    except Exception:
        db.rollback()
        for item in reversed(staged):
            item.original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item.staged, item.original)
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    deleted_files = sum(item.file_count for item in staged)
    freed_bytes = sum(item.byte_count for item in staged)
    shutil.rmtree(staging_root, ignore_errors=True)
    cleanup_parent = staging_root.parent
    try:
        cleanup_parent.rmdir()
    except OSError:
        pass
    logger.info(
        "project cleanup completed project_id=%s deleted_files=%s freed_bytes=%s",
        project.id,
        deleted_files,
        freed_bytes,
    )
    return CleanupResult(project.id, deleted_files, freed_bytes)
