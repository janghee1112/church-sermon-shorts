from pydantic import BaseModel, Field


class SubtitleLayoutPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    subtitle_font_scale: float = Field(default=0.9, ge=0.7, le=1.5)


class SubtitleLayoutPreviewResponse(BaseModel):
    canvas_width: int
    canvas_height: int
    font_size_px: int
    line_height_px: int
    lines: list[str]
    font_key: str
    font_name: str
