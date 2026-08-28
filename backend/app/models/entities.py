from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
from app.database.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_file_name: Mapped[str] = mapped_column(String(500))
    stored_file_path: Mapped[str] = mapped_column(String(1000))
    original_object_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, index=True)
    original_content_type: Mapped[str] = mapped_column(String(120), default="video/mp4", server_default="video/mp4")
    duration_seconds: Mapped[float] = mapped_column(Float)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    file_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="uploaded", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=10)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_stage: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    analysis_mode: Mapped[str] = mapped_column(String(16), default="mock", server_default="mock")
    transcription_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    transcript_segment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    transcript_char_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sermon_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sermon_topics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    segments: Mapped[List["TranscriptSegment"]] = relationship(cascade="all, delete-orphan", back_populates="project")
    words: Mapped[List["TranscriptWord"]] = relationship(cascade="all, delete-orphan", back_populates="project")
    candidates: Mapped[List["ClipCandidate"]] = relationship(cascade="all, delete-orphan", back_populates="project")
    drafts: Mapped[List["ClipDraft"]] = relationship(cascade="all, delete-orphan", back_populates="project")
    renders: Mapped[List["RenderJob"]] = relationship(cascade="all, delete-orphan", back_populates="project")
    upload_sessions: Mapped[List["MultipartUploadSession"]] = relationship(
        cascade="all, delete-orphan", back_populates="project"
    )


class MultipartUploadSession(Base):
    __tablename__ = "multipart_upload_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider_upload_id: Mapped[str] = mapped_column(String(1000), unique=True)
    object_key: Mapped[str] = mapped_column(String(1000), unique=True)
    expected_file_size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(120))
    part_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="uploading", server_default="uploading", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="upload_sessions")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    segment_order: Mapped[int] = mapped_column(Integer)

    project: Mapped[Project] = relationship(back_populates="segments")
    words: Mapped[List["TranscriptWord"]] = relationship(cascade="all, delete-orphan", back_populates="segment")


class TranscriptWord(Base):
    __tablename__ = "transcript_words"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    segment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=True)
    word: Mapped[str] = mapped_column(String(300))
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    word_order: Mapped[int] = mapped_column(Integer)

    project: Mapped[Project] = relationship(back_populates="words")
    segment: Mapped[Optional[TranscriptSegment]] = relationship(back_populates="words")


class ClipCandidate(Base):
    __tablename__ = "clip_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    candidate_order: Mapped[int] = mapped_column(Integer)
    recommendation_type: Mapped[str] = mapped_column(String(80), default="핵심 메시지")
    start_segment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transcript_segments.id"), nullable=True)
    end_segment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transcript_segments.id"), nullable=True)
    segment_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    duration_sec: Mapped[float] = mapped_column(Float)
    transcript: Mapped[str] = mapped_column(Text)
    main_topic: Mapped[str] = mapped_column(String(300))
    selection_reason: Mapped[str] = mapped_column(Text)
    centrality_score: Mapped[int] = mapped_column(Integer)
    standalone_score: Mapped[int] = mapped_column(Integer)
    hook_score: Mapped[int] = mapped_column(Integer)
    emotional_score: Mapped[int] = mapped_column(Integer)
    overall_score: Mapped[int] = mapped_column(Integer)
    analysis_metadata: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")

    project: Mapped[Project] = relationship(back_populates="candidates")
    titles: Mapped[List["CandidateTitle"]] = relationship(cascade="all, delete-orphan", back_populates="candidate")
    drafts: Mapped[List["ClipDraft"]] = relationship(cascade="all, delete-orphan", back_populates="candidate")


class CandidateTitle(Base):
    __tablename__ = "candidate_titles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("clip_candidates.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    title_type: Mapped[str] = mapped_column(String(80))
    title_order: Mapped[int] = mapped_column(Integer)

    candidate: Mapped[ClipCandidate] = relationship(back_populates="titles")


class ClipDraft(Base):
    __tablename__ = "clip_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("clip_candidates.id", ondelete="CASCADE"), unique=True, index=True)
    start_segment_id: Mapped[int] = mapped_column(ForeignKey("transcript_segments.id"))
    end_segment_id: Mapped[int] = mapped_column(ForeignKey("transcript_segments.id"))
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    duration_sec: Mapped[float] = mapped_column(Float)
    custom_title: Mapped[str] = mapped_column(String(500), default="", server_default="")
    title_highlight_text: Mapped[str] = mapped_column(String(500), default="", server_default="")
    title_highlight_ranges: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    zoom_scale: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_ZOOM_SCALE, server_default="1.30")
    crop_position_x: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_CROP_POSITION_X, server_default="0.50")
    crop_position_y: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_CROP_POSITION_Y, server_default="0.70")
    video_area_position_y: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_VIDEO_AREA_POSITION_Y, server_default="0.28")
    video_area_height: Mapped[float] = mapped_column(Float, default=0.48, server_default="0.48")
    title_font_scale: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_TITLE_FONT_SCALE, server_default="1.00")
    title_position_y: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_TITLE_POSITION_Y, server_default="0.08")
    subtitle_font_scale: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_SUBTITLE_FONT_SCALE, server_default="0.90")
    subtitle_position_y: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_SUBTITLE_POSITION_Y, server_default="0.52")
    playback_rate: Mapped[float] = mapped_column(Float, default=SERMON_LETTERBOX_PLAYBACK_RATE, server_default="1.20")
    background_darkness: Mapped[float] = mapped_column(Float, default=0.55, server_default="0.55")
    subject_brightness: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    subject_mask_enabled: Mapped[bool] = mapped_column(default=True, server_default="1")
    subject_mask_feather: Mapped[float] = mapped_column(Float, default=0.12, server_default="0.12")
    subject_mask_threshold: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    template_type: Mapped[str] = mapped_column(String(40), default="sermon_letterbox_v1", server_default="sermon_letterbox_v1")
    status: Mapped[str] = mapped_column(String(20), default="editing", server_default="editing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="drafts")
    candidate: Mapped[ClipCandidate] = relationship(back_populates="drafts")
    subtitles: Mapped[List["DraftSubtitle"]] = relationship(
        cascade="all, delete-orphan", back_populates="draft", order_by="DraftSubtitle.cue_order"
    )
    renders: Mapped[List["RenderJob"]] = relationship(cascade="all, delete-orphan", back_populates="draft")


class DraftSubtitle(Base):
    __tablename__ = "draft_subtitles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("clip_drafts.id", ondelete="CASCADE"), index=True)
    cue_order: Mapped[int] = mapped_column(Integer)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    original_text: Mapped[str] = mapped_column(Text)
    edited_text: Mapped[str] = mapped_column(Text)
    is_edited: Mapped[bool] = mapped_column(default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    draft: Mapped[ClipDraft] = relationship(back_populates="subtitles")


class RenderJob(Base):
    __tablename__ = "render_jobs"
    __table_args__ = (UniqueConstraint("draft_id", "version", name="uq_render_job_draft_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("clip_drafts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    current_step: Mapped[str] = mapped_column(String(40), default="validating", server_default="validating")
    output_file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    output_object_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, index=True)
    output_file_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    output_file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings_snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped[Project] = relationship(back_populates="renders")
    draft: Mapped[ClipDraft] = relationship(back_populates="renders")
