from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.subtitle_layout import SubtitleLayoutPreviewRequest, SubtitleLayoutPreviewResponse
from app.services.subtitle_renderer import calculate_subtitle_layout


router = APIRouter(tags=["subtitle-layout"])


@router.post("/api/subtitle-layout/preview", response_model=SubtitleLayoutPreviewResponse)
def preview_subtitle_layout(payload: SubtitleLayoutPreviewRequest) -> dict:
    settings = get_settings()
    try:
        layout = calculate_subtitle_layout(
            payload.text,
            settings.subtitle_font_path,
            round(52 * payload.subtitle_font_scale),
            settings.render_width,
        )
        return {
            "canvas_width": settings.render_width,
            "canvas_height": settings.render_height,
            **layout,
            "font_key": "korean_gothic_v1",
            "font_name": settings.subtitle_font_name,
        }
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="자막 레이아웃을 계산하지 못했습니다.") from exc
