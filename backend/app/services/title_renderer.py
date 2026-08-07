from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from app.services.title_highlight import normalize_highlight_ranges


TITLE_BASE_FONT_SIZE_PX = 84
TITLE_MIN_FONT_SIZE_PX = 36
TITLE_FONT_SIZE_STEP_PX = 2
TITLE_LINE_HEIGHT_RATIO = 1.08
TITLE_LETTER_SPACING_EM = -0.03
TITLE_AREA_LEFT_RATIO = 0.07
TITLE_AREA_WIDTH_RATIO = 0.86
TITLE_AREA_HEIGHT_RATIO = 0.23
TITLE_POSITION_MIN_RATIO = 0.04
TITLE_POSITION_MAX_RATIO = 0.28
TITLE_TEXT_COLOR = "#FFFFFF"
TITLE_HIGHLIGHT_COLOR = "#FFD84D"


class TitleRenderError(Exception):
    pass


@dataclass(frozen=True)
class TitleLine:
    text: str
    source_start: int
    source_end: int
    width_px: float


@dataclass(frozen=True)
class TitleArea:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TitleLayout:
    canvas_width: int
    canvas_height: int
    initial_font_size_px: int
    font_size_px: int
    line_height_px: int
    total_height_px: int
    auto_fit_applied: bool
    character_wrap_applied: bool
    area: TitleArea
    lines: tuple[TitleLine, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TitleLayout":
        area = value["area"]
        return cls(
            canvas_width=int(value["canvas_width"]),
            canvas_height=int(value["canvas_height"]),
            initial_font_size_px=int(value["initial_font_size_px"]),
            font_size_px=int(value["font_size_px"]),
            line_height_px=int(value["line_height_px"]),
            total_height_px=int(value["total_height_px"]),
            auto_fit_applied=bool(value["auto_fit_applied"]),
            character_wrap_applied=bool(value["character_wrap_applied"]),
            area=TitleArea(
                x=int(area["x"]), y=int(area["y"]),
                width=int(area["width"]), height=int(area["height"]),
            ),
            lines=tuple(
                TitleLine(
                    text=str(line["text"]),
                    source_start=int(line["source_start"]),
                    source_end=int(line["source_end"]),
                    width_px=float(line["width_px"]),
                )
                for line in value["lines"]
            ),
        )


def _text_width(draw: Any, text: str, font: Any) -> float:
    if not text:
        return 0.0
    spacing = font.size * TITLE_LETTER_SPACING_EM
    return float(sum(draw.textlength(character, font=font) for character in text) + spacing * (len(text) - 1))


def _line(draw: Any, text: str, source_start: int, font: Any) -> TitleLine:
    return TitleLine(
        text=text,
        source_start=source_start,
        source_end=source_start + len(text),
        width_px=_text_width(draw, text, font),
    )


def _split_overwide_line(draw: Any, line: TitleLine, font: Any, max_width: int) -> list[TitleLine]:
    if not line.text or line.width_px <= max_width:
        return [line]
    chunks: list[TitleLine] = []
    chunk_start = 0
    while chunk_start < len(line.text):
        best_end = chunk_start + 1
        for chunk_end in range(chunk_start + 1, len(line.text) + 1):
            if _text_width(draw, line.text[chunk_start:chunk_end], font) <= max_width:
                best_end = chunk_end
                continue
            break
        chunks.append(_line(draw, line.text[chunk_start:best_end], line.source_start + chunk_start, font))
        chunk_start = best_end
    return chunks


def _wrap_paragraph(
    draw: Any,
    paragraph: str,
    offset: int,
    font: Any,
    max_width: int,
    allow_character_wrap: bool,
) -> list[TitleLine]:
    if not paragraph:
        return [_line(draw, "", offset, font)]
    words = list(re.finditer(r"\S+", paragraph))
    if not words:
        return [_line(draw, paragraph, offset, font)]

    lines: list[TitleLine] = []
    current_start = words[0].start()
    current_end = words[0].end()
    for word in words[1:]:
        candidate = paragraph[current_start:word.end()]
        if _text_width(draw, candidate, font) <= max_width:
            current_end = word.end()
            continue
        lines.append(_line(draw, paragraph[current_start:current_end], offset + current_start, font))
        current_start = word.start()
        current_end = word.end()
    lines.append(_line(draw, paragraph[current_start:current_end], offset + current_start, font))

    if not allow_character_wrap:
        return lines
    bounded: list[TitleLine] = []
    for line in lines:
        bounded.extend(_split_overwide_line(draw, line, font, max_width))
    return bounded


def _layout_lines(
    draw: Any,
    title: str,
    font: Any,
    max_width: int,
    allow_character_wrap: bool,
) -> list[TitleLine]:
    lines: list[TitleLine] = []
    offset = 0
    for paragraph in title.split("\n"):
        lines.extend(_wrap_paragraph(draw, paragraph, offset, font, max_width, allow_character_wrap))
        offset += len(paragraph) + 1
    return lines


def calculate_title_layout(
    title: str,
    font_path: Path,
    canvas_width: int,
    canvas_height: int,
    font_scale: float,
    position_y: float,
) -> TitleLayout:
    """Return the canonical 1080x1920 title layout used by preview and MP4."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise TitleRenderError("제목 이미지 렌더러를 불러오지 못했습니다.") from exc
    if not font_path.is_file():
        raise TitleRenderError("렌더링에 사용할 제목 글꼴을 찾을 수 없습니다.")

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    area = TitleArea(
        x=round(canvas_width * TITLE_AREA_LEFT_RATIO),
        y=round(min(TITLE_POSITION_MAX_RATIO, max(TITLE_POSITION_MIN_RATIO, position_y)) * canvas_height),
        width=round(canvas_width * TITLE_AREA_WIDTH_RATIO),
        height=round(canvas_height * TITLE_AREA_HEIGHT_RATIO),
    )
    initial_size = round(TITLE_BASE_FONT_SIZE_PX * min(1.5, max(0.7, font_scale)))
    if not title:
        return TitleLayout(
            canvas_width, canvas_height, initial_size, initial_size,
            round(initial_size * TITLE_LINE_HEIGHT_RATIO), 0, False, False, area, (),
        )

    selected_font_size = initial_size
    selected_lines: list[TitleLine] = []
    character_wrap_applied = False
    for size in range(initial_size, TITLE_MIN_FONT_SIZE_PX - 1, -TITLE_FONT_SIZE_STEP_PX):
        font = ImageFont.truetype(str(font_path), size=size)
        lines = _layout_lines(measure, title, font, area.width, allow_character_wrap=False)
        line_height = round(size * TITLE_LINE_HEIGHT_RATIO)
        if all(line.width_px <= area.width for line in lines) and len(lines) * line_height <= area.height:
            selected_font_size = size
            selected_lines = lines
            break
    else:
        selected_font_size = TITLE_MIN_FONT_SIZE_PX
        font = ImageFont.truetype(str(font_path), size=selected_font_size)
        selected_lines = _layout_lines(measure, title, font, area.width, allow_character_wrap=True)
        character_wrap_applied = True

    line_height = round(selected_font_size * TITLE_LINE_HEIGHT_RATIO)
    return TitleLayout(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        initial_font_size_px=initial_size,
        font_size_px=selected_font_size,
        line_height_px=line_height,
        total_height_px=len(selected_lines) * line_height,
        auto_fit_applied=selected_font_size != initial_size or character_wrap_applied,
        character_wrap_applied=character_wrap_applied,
        area=area,
        lines=tuple(selected_lines),
    )


def render_title_image(
    title: str,
    highlight_ranges: list[dict[str, int]],
    font_path: Path,
    layout: TitleLayout,
) -> Any:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise TitleRenderError("제목 이미지 렌더러를 불러오지 못했습니다.") from exc

    image = Image.new("RGBA", (layout.canvas_width, layout.canvas_height), (0, 0, 0, 0))
    if not title or not layout.lines:
        return image
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), size=layout.font_size_px)
    try:
        normalized_ranges = normalize_highlight_ranges(title, highlight_ranges)
    except ValueError as exc:
        raise TitleRenderError("큰 제목의 강조 범위가 올바르지 않습니다.") from exc

    y = layout.area.y
    for line in layout.lines:
        x = (layout.canvas_width - line.width_px) / 2
        cursor_x = x
        spacing = font.size * TITLE_LETTER_SPACING_EM
        for index, character in enumerate(line.text):
            source_index = line.source_start + index
            emphasized = any(item["start"] <= source_index < item["end"] for item in normalized_ranges)
            draw.text(
                (cursor_x, y), character, font=font,
                fill=TITLE_HIGHLIGHT_COLOR if emphasized else TITLE_TEXT_COLOR,
            )
            cursor_x += float(draw.textlength(character, font=font))
            if index < len(line.text) - 1:
                cursor_x += spacing
        y += layout.line_height_px
    return image


def title_preview_data_url(
    title: str,
    highlight_ranges: list[dict[str, int]],
    font_path: Path,
    layout: TitleLayout,
) -> str:
    buffer = BytesIO()
    render_title_image(title, highlight_ranges, font_path, layout).save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def render_title_png(
    output_path: Path,
    title: str,
    highlight_ranges: list[dict[str, int]],
    font_path: Path,
    canvas_width: int,
    canvas_height: int,
    font_scale: float,
    position_y: float,
    layout: TitleLayout | None = None,
) -> TitleLayout:
    final_layout = layout or calculate_title_layout(
        title, font_path, canvas_width, canvas_height, font_scale, position_y,
    )
    if final_layout.canvas_width != canvas_width or final_layout.canvas_height != canvas_height:
        raise TitleRenderError("제목 레이아웃의 출력 해상도가 올바르지 않습니다.")
    render_title_image(title, highlight_ranges, font_path, final_layout).save(output_path, format="PNG")
    return final_layout
