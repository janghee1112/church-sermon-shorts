from typing import Generator

import json

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.template_defaults import (
    LEGACY_SUBTITLE_POSITION_Y,
    LEGACY_VIDEO_AREA_POSITION_Y,
    SERMON_LETTERBOX_TITLE_POSITION_Y,
)


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _add_mvp_columns()


def _add_mvp_columns(target_engine: Engine = engine) -> None:
    """Small idempotent migration for the local SQLite MVP database."""
    if target_engine.dialect.name != "sqlite":
        return
    title_ranges_added = False
    additions = {
        "projects": {
            "original_object_key": "VARCHAR(1000)",
            "original_content_type": "VARCHAR(120) NOT NULL DEFAULT 'video/mp4'",
            "analysis_mode": "VARCHAR(16) NOT NULL DEFAULT 'mock'",
            "transcription_model": "VARCHAR(120)",
            "transcript_segment_count": "INTEGER NOT NULL DEFAULT 0",
            "transcript_char_count": "INTEGER NOT NULL DEFAULT 0",
        },
        "clip_candidates": {
            "start_segment_id": "INTEGER",
            "end_segment_id": "INTEGER",
            "segment_count": "INTEGER NOT NULL DEFAULT 0",
            "analysis_metadata": "TEXT NOT NULL DEFAULT '{}'",
        },
        "clip_drafts": {
            "title_highlight_text": "VARCHAR(500) NOT NULL DEFAULT ''",
            "title_highlight_ranges": "TEXT NOT NULL DEFAULT '[]'",
            "zoom_scale": "FLOAT NOT NULL DEFAULT 1.12",
            "crop_position_y": "FLOAT NOT NULL DEFAULT 0.6",
            "video_area_position_y": f"FLOAT NOT NULL DEFAULT {LEGACY_VIDEO_AREA_POSITION_Y}",
            "video_area_height": "FLOAT NOT NULL DEFAULT 0.48",
            "title_font_scale": "FLOAT NOT NULL DEFAULT 1.0",
            "title_position_y": f"FLOAT NOT NULL DEFAULT {SERMON_LETTERBOX_TITLE_POSITION_Y}",
            "subtitle_font_scale": "FLOAT NOT NULL DEFAULT 1.0",
            "subtitle_position_y": f"FLOAT NOT NULL DEFAULT {LEGACY_SUBTITLE_POSITION_Y}",
            "playback_rate": "FLOAT NOT NULL DEFAULT 1.0",
            "background_darkness": "FLOAT NOT NULL DEFAULT 0.55",
            "subject_brightness": "FLOAT NOT NULL DEFAULT 1.0",
            "subject_mask_enabled": "BOOLEAN NOT NULL DEFAULT 1",
            "subject_mask_feather": "FLOAT NOT NULL DEFAULT 0.12",
            "subject_mask_threshold": "FLOAT NOT NULL DEFAULT 0.5",
            "template_type": "VARCHAR(40) NOT NULL DEFAULT 'sermon_letterbox_v1'",
        },
        "render_jobs": {
            "output_object_key": "VARCHAR(1000)",
        },
    }
    inspector = inspect(target_engine)
    with target_engine.begin() as connection:
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )
                    if table_name == "clip_drafts" and column_name == "title_highlight_ranges":
                        title_ranges_added = True
        if title_ranges_added:
            rows = connection.exec_driver_sql(
                "SELECT id, custom_title, title_highlight_text FROM clip_drafts"
            ).mappings()
            for row in rows:
                title = row["custom_title"] or ""
                highlight = row["title_highlight_text"] or ""
                start = title.find(highlight) if highlight else -1
                ranges = [] if start < 0 else [{"start": start, "end": start + len(highlight)}]
                connection.exec_driver_sql(
                    "UPDATE clip_drafts SET title_highlight_ranges = ? WHERE id = ?",
                    (json.dumps(ranges, ensure_ascii=False, separators=(",", ":")), row["id"]),
                )
        if inspector.has_table("projects") and inspector.has_table("transcript_segments"):
            connection.exec_driver_sql(
                """
                UPDATE projects
                SET transcript_segment_count = (
                        SELECT COUNT(*) FROM transcript_segments
                        WHERE transcript_segments.project_id = projects.id
                    ),
                    transcript_char_count = COALESCE((
                        SELECT SUM(LENGTH(text)) FROM transcript_segments
                        WHERE transcript_segments.project_id = projects.id
                    ), 0),
                    transcription_model = CASE
                        WHEN analysis_mode = 'mock' AND transcription_model IS NULL THEN 'mock-transcription'
                        ELSE transcription_model
                    END
                """
            )
        if inspector.has_table("clip_drafts"):
            connection.exec_driver_sql(
                """
                UPDATE clip_drafts
                SET zoom_scale = CASE
                        WHEN zoom_scale > 1.4 THEN 1.4
                        WHEN zoom_scale < 1.0 THEN 1.0
                        ELSE zoom_scale
                    END,
                    subtitle_position_y = CASE
                        WHEN template_type = 'sermon_focus_v1' AND subtitle_position_y > 0.28 THEN 0.25
                        ELSE subtitle_position_y
                    END,
                    template_type = 'sermon_letterbox_v1'
                """
            )
