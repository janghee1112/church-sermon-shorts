from pathlib import Path
from typing import Iterable, Mapping

from app.core.template_defaults import SERMON_LETTERBOX_SUBTITLE_POSITION_MAX


def _ass_time(seconds: float) -> str:
    total = max(0, round(seconds * 100))
    hours, remainder = divmod(total, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass_text(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\n", r"\N")
        .replace("\r", r"\N")
    )


def build_relative_cues(
    cues: Iterable[Mapping[str, object]], start_sec: float, end_sec: float, playback_rate: float = 1.0
) -> list[dict[str, object]]:
    if playback_rate <= 0:
        raise ValueError("재생 속도가 올바르지 않습니다.")
    source_duration = end_sec - start_sec
    output_duration = source_duration / playback_rate
    relative: list[dict[str, object]] = []
    for cue in cues:
        cue_start = max(0.0, float(cue["start_sec"]) - start_sec) / playback_rate
        cue_end = min(source_duration, float(cue["end_sec"]) - start_sec) / playback_rate
        cue_end = min(output_duration, cue_end)
        text = str(cue.get("edited_text") or cue.get("original_text") or "").strip()
        if text and cue_end > cue_start:
            relative.append({"start_sec": cue_start, "end_sec": cue_end, "text": text})
    return relative


def write_ass_subtitles(
    path: Path,
    cues: Iterable[Mapping[str, object]],
    canvas_width: int,
    canvas_height: int,
    font_name: str,
    font_size: int,
    position_y: float,
) -> None:
    y = round(min(SERMON_LETTERBOX_SUBTITLE_POSITION_MAX, max(0.18, position_y)) * canvas_height)
    outline = max(1, round(font_size * 0.025))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_width}
PlayResY: {canvas_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sermon,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},1,8,65,65,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue in cues:
        events.append(
            "Dialogue: 0,{start},{end},Sermon,,0,0,0,,{{\\an8\\pos({x},{y})}}{text}".format(
                start=_ass_time(float(cue["start_sec"])),
                end=_ass_time(float(cue["end_sec"])),
                x=canvas_width // 2,
                y=y,
                text=_escape_ass_text(str(cue["text"])),
            )
        )
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render_subtitle_images(
    output_directory: Path,
    cues: Iterable[Mapping[str, object]],
    canvas_width: int,
    canvas_height: int,
    font_path: Path,
    font_size: int,
    position_y: float,
) -> list[tuple[Path, float, float]]:
    from PIL import Image, ImageDraw, ImageFont

    rendered: list[tuple[Path, float, float]] = []
    max_width = round(canvas_width * 0.88)
    y = round(min(SERMON_LETTERBOX_SUBTITLE_POSITION_MAX, max(0.18, position_y)) * canvas_height)
    for index, cue in enumerate(cues, start=1):
        text = str(cue["text"])
        selected_font = None
        selected_lines: list[str] = []
        for size in range(font_size, 35, -2):
            font = ImageFont.truetype(str(font_path), size=size)
            lines: list[str] = []
            for manual_line in text.splitlines() or [text]:
                words = manual_line.split()
                if not words:
                    lines.append("")
                    continue
                current = words[0]
                for word in words[1:]:
                    candidate = f"{current} {word}"
                    if ImageDraw.Draw(Image.new("L", (1, 1))).textlength(candidate, font=font) <= max_width:
                        current = candidate
                    else:
                        lines.append(current)
                        current = word
                lines.append(current)
            if len(lines) <= 2 and all(
                ImageDraw.Draw(Image.new("L", (1, 1))).textlength(line, font=font) <= max_width
                for line in lines
            ):
                selected_font = font
                selected_lines = lines
                break
        if selected_font is None:
            selected_font = ImageFont.truetype(str(font_path), size=36)
            selected_lines = text.splitlines() or [text]
        image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        line_height = round(selected_font.size * 1.28)
        stroke = max(1, round(selected_font.size * 0.025))
        line_y = y
        for line in selected_lines:
            width = draw.textlength(line, font=selected_font)
            draw.text(
                ((canvas_width - width) / 2, line_y), line, font=selected_font,
                fill="#FFFFFF", stroke_width=stroke, stroke_fill="#000000",
            )
            line_y += line_height
        path = output_directory / f"subtitle_{index:03d}.png"
        image.save(path, format="PNG")
        rendered.append((path, float(cue["start_sec"]), float(cue["end_sec"])))
    return rendered


def render_subtitle_timeline(
    output_directory: Path,
    cues: Iterable[Mapping[str, object]],
    canvas_width: int,
    canvas_height: int,
    font_path: Path,
    font_size: int,
    position_y: float,
    duration_sec: float,
    title_path: Path,
    banner_path: Path,
    banner_width: int,
    banner_height: int,
    banner_x: int,
    banner_y: int,
) -> tuple[Path, list[Path]]:
    from PIL import Image

    rendered = render_subtitle_images(
        output_directory, cues, canvas_width, canvas_height, font_path, font_size, position_y,
    )
    decoration_path = output_directory / "decoration.png"
    with Image.open(title_path).convert("RGBA") as decoration, Image.open(banner_path).convert("RGBA") as banner:
        resized_banner = banner.resize((banner_width, banner_height), Image.Resampling.LANCZOS)
        decoration.alpha_composite(resized_banner, dest=(banner_x, banner_y))
        decoration.save(decoration_path, format="PNG")

    composited: list[tuple[Path, float, float]] = []
    with Image.open(decoration_path).convert("RGBA") as decoration:
        for index, (subtitle_path, cue_start, cue_end) in enumerate(rendered, start=1):
            with Image.open(subtitle_path).convert("RGBA") as subtitle:
                overlay = Image.alpha_composite(decoration, subtitle)
            overlay_path = output_directory / f"overlay_{index:03d}.png"
            overlay.save(overlay_path, format="PNG")
            subtitle_path.unlink(missing_ok=True)
            composited.append((overlay_path, cue_start, cue_end))

    manifest_path = output_directory / "overlays.ffconcat"
    lines = ["ffconcat version 1.0"]
    cursor = 0.0
    assets = [decoration_path]

    for image_path, cue_start, cue_end in sorted(composited, key=lambda item: item[1]):
        start = max(cursor, min(duration_sec, cue_start))
        end = max(start, min(duration_sec, cue_end))
        if start > cursor + 0.001:
            lines.extend([f"file '{decoration_path.name}'", f"duration {start - cursor:.6f}"])
        if end > start + 0.001:
            lines.extend([f"file '{image_path.name}'", f"duration {end - start:.6f}"])
            cursor = end
        assets.append(image_path)

    if duration_sec > cursor + 0.001:
        lines.extend([f"file '{decoration_path.name}'", f"duration {duration_sec - cursor:.6f}"])
    lines.append(f"file '{decoration_path.name}'")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path, assets
