"""Copy legacy local media to R2 without deleting the original files."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import SessionLocal, init_db
from app.models import Project, RenderJob
from app.services.storage_service import get_storage_service, project_original_key, project_render_key


def main() -> None:
    settings = get_settings()
    if not settings.uses_r2:
        raise SystemExit("STORAGE_BACKEND=r2로 설정한 뒤 실행하세요.")
    init_db()
    storage = get_storage_service(settings)
    copied = 0
    with SessionLocal() as db:
        projects = db.scalars(select(Project).order_by(Project.created_at)).all()
        for project in projects:
            if not project.original_object_key and project.stored_file_path:
                source = Path(project.stored_file_path)
                if source.is_file():
                    key = project_original_key(project.id)
                    metadata = storage.upload_file(source, key, project.original_content_type or "video/mp4")
                    if metadata.size != source.stat().st_size:
                        raise SystemExit(f"원본 크기 검증 실패: {project.id}")
                    project.original_object_key = key
                    copied += 1
            renders = db.scalars(
                select(RenderJob).where(RenderJob.project_id == project.id).order_by(RenderJob.version)
            ).all()
            for render in renders:
                if render.output_object_key or not render.output_file_path:
                    continue
                source = Path(render.output_file_path)
                if not source.is_file():
                    continue
                file_name = render.output_file_name or source.name
                key = project_render_key(project.id, render.version, file_name)
                metadata = storage.upload_file(source, key, "video/mp4")
                if metadata.size != source.stat().st_size:
                    raise SystemExit(f"렌더 크기 검증 실패: {render.id}")
                render.output_object_key = key
                copied += 1
            db.commit()
    print(f"R2 copy complete: {copied} object(s). Local files were preserved.")


if __name__ == "__main__":
    main()
