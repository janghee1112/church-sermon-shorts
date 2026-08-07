from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.title_layout import TitleLayoutPreviewRequest, TitleLayoutPreviewResponse
from app.services.title_renderer import (
    TitleRenderError,
    calculate_title_layout,
    title_preview_data_url,
)


router = APIRouter(tags=["title-layout"])


@router.post("/api/title-layout/preview", response_model=TitleLayoutPreviewResponse)
def preview_title_layout(payload: TitleLayoutPreviewRequest) -> dict:
    settings = get_settings()
    ranges = [item.model_dump() for item in payload.title_highlight_ranges]
    try:
        layout = calculate_title_layout(
            payload.title,
            settings.title_font_path,
            settings.render_width,
            settings.render_height,
            payload.title_font_scale,
            payload.title_position_y,
        )
        return {
            **layout.to_dict(),
            "font_key": "pretendard_black_v1",
            "font_name": settings.title_font_name,
            "image_data_url": title_preview_data_url(
                payload.title, ranges, settings.title_font_path, layout,
            ),
        }
    except TitleRenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
