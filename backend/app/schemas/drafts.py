from datetime import datetime
import math
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class TitleHighlightRangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> "TitleHighlightRangeRequest":
        if self.end <= self.start:
            raise ValueError("제목 강조 종료 위치는 시작 위치보다 뒤여야 합니다.")
        return self


class TitleHighlightRangeResponse(BaseModel):
    start: int
    end: int


class DraftCreateRequest(BaseModel):
    candidate_id: int = Field(gt=0)
    selected_title_order: Optional[int] = Field(default=None, ge=1, le=3)


class DraftPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    custom_title: Optional[str] = Field(default=None, max_length=60)
    title_highlight_text: Optional[str] = Field(default=None, max_length=60)
    title_highlight_ranges: Optional[List[TitleHighlightRangeRequest]] = None
    zoom_scale: Optional[float] = Field(default=None, ge=1.0, le=1.4)
    crop_position_x: Optional[float] = Field(default=None, ge=0, le=1)
    crop_position_y: Optional[float] = Field(default=None, ge=0, le=1)
    video_area_position_y: Optional[float] = Field(default=None, ge=0.28, le=0.45)
    video_area_height: Optional[float] = Field(default=None, ge=0.38, le=0.58)
    title_font_scale: Optional[float] = Field(default=None, ge=0.7, le=1.5)
    title_position_y: Optional[float] = Field(default=None, ge=0.04, le=0.28)
    subtitle_font_scale: Optional[float] = Field(default=None, ge=0.7, le=1.5)
    subtitle_position_y: Optional[float] = Field(default=None, ge=0.18, le=0.5)
    playback_rate: Optional[float] = Field(default=None, ge=0.75, le=1.5, allow_inf_nan=False)
    template_type: Optional[Literal["sermon_letterbox_v1"]] = None
    status: Optional[Literal["editing", "ready"]] = None

    @field_validator("custom_title", "title_highlight_text")
    @classmethod
    def sanitize_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = re.sub(r"<[^>]*>", "", value).strip()
        if len(cleaned) > 60:
            raise ValueError("쇼츠 큰 제목은 60자 이하여야 합니다.")
        return cleaned

    @field_validator("playback_rate", mode="before")
    @classmethod
    def validate_playback_rate(cls, value: object) -> object:
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("재생 속도는 숫자여야 합니다.")
        if not math.isfinite(float(value)):
            raise ValueError("재생 속도는 유한한 숫자여야 합니다.")
        return value


class DraftRangeRequest(BaseModel):
    start_segment_id: int = Field(gt=0)
    end_segment_id: int = Field(gt=0)
    regenerate_subtitles: bool = True


class SubtitleSaveItem(BaseModel):
    id: int = Field(gt=0)
    cue_order: int = Field(gt=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    edited_text: str

    @model_validator(mode="after")
    def validate_times(self) -> "SubtitleSaveItem":
        if self.end_sec <= self.start_sec:
            raise ValueError("자막 종료 시간은 시작 시간보다 뒤여야 합니다.")
        return self


class SubtitlePutRequest(BaseModel):
    subtitles: List[SubtitleSaveItem] = Field(min_length=1)


class SubtitlePatchRequest(BaseModel):
    edited_text: Optional[str] = None
    start_sec: Optional[float] = Field(default=None, ge=0)
    end_sec: Optional[float] = Field(default=None, gt=0)


class SubtitleSplitRequest(BaseModel):
    split_index: int = Field(gt=0)


class SubtitleMergeRequest(BaseModel):
    first_subtitle_id: int = Field(gt=0)
    second_subtitle_id: int = Field(gt=0)


class DraftCandidateResponse(BaseModel):
    id: int
    candidate_order: int
    main_topic: str
    recommended_start_segment_id: int
    recommended_end_segment_id: int
    recommended_start_sec: float
    recommended_end_sec: float
    title_placeholder: str = ""


class DraftRangeResponse(BaseModel):
    start_segment_id: int
    end_segment_id: int
    start_sec: float
    end_sec: float
    duration_sec: float


class DraftSubtitleResponse(BaseModel):
    id: int
    cue_order: int
    start_sec: float
    end_sec: float
    relative_start_sec: float
    relative_end_sec: float
    original_text: str
    edited_text: str
    is_edited: bool


class DraftResponse(BaseModel):
    id: int
    project_id: str
    project_original_file_name: str
    analysis_mode: str
    candidate_id: int
    candidate: DraftCandidateResponse
    range: DraftRangeResponse
    custom_title: str
    title_highlight_text: str
    title_highlight_ranges: List[TitleHighlightRangeResponse]
    zoom_scale: float
    crop_position_x: float
    crop_position_y: float
    video_area_position_y: float
    video_area_height: float
    title_font_scale: float
    title_position_y: float
    subtitle_font_scale: float
    subtitle_position_y: float
    playback_rate: float
    template_type: str
    status: str
    subtitles: List[DraftSubtitleResponse]
    updated_at: datetime
