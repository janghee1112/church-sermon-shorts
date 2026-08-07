from typing import List

from pydantic import BaseModel, ConfigDict, Field

from app.core.template_defaults import SERMON_LETTERBOX_TITLE_POSITION_Y
from app.schemas.drafts import TitleHighlightRangeRequest


class TitleLayoutPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=60)
    title_font_scale: float = Field(default=1.0, ge=0.7, le=1.5)
    title_position_y: float = Field(default=SERMON_LETTERBOX_TITLE_POSITION_Y, ge=0.04, le=0.28)
    title_highlight_ranges: List[TitleHighlightRangeRequest] = Field(default_factory=list)


class TitleLayoutLineResponse(BaseModel):
    text: str
    source_start: int
    source_end: int
    width_px: float


class TitleLayoutAreaResponse(BaseModel):
    x: int
    y: int
    width: int
    height: int


class TitleLayoutPreviewResponse(BaseModel):
    canvas_width: int
    canvas_height: int
    initial_font_size_px: int
    font_size_px: int
    line_height_px: int
    total_height_px: int
    auto_fit_applied: bool
    character_wrap_applied: bool
    area: TitleLayoutAreaResponse
    lines: List[TitleLayoutLineResponse]
    font_key: str
    font_name: str
    image_data_url: str
