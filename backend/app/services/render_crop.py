from dataclasses import dataclass


@dataclass(frozen=True)
class RenderCrop:
    scale: float
    scaled_width: float
    scaled_height: float
    crop_x: float
    crop_y: float
    crop_width: float
    crop_height: float


def calculate_render_crop(
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    zoom_scale: float,
    crop_position_x: float,
    crop_position_y: float,
) -> RenderCrop:
    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("영상 크기는 0보다 커야 합니다.")
    zoom = min(1.4, max(1.0, zoom_scale))
    position_x = min(1.0, max(0.0, crop_position_x))
    position_y = min(1.0, max(0.0, crop_position_y))
    cover_scale = max(target_width / source_width, target_height / source_height)
    render_scale = cover_scale * zoom
    crop_width = min(float(source_width), target_width / render_scale)
    crop_height = min(float(source_height), target_height / render_scale)
    crop_x = max(0.0, (source_width - crop_width) * position_x)
    crop_y = max(0.0, (source_height - crop_height) * position_y)
    return RenderCrop(
        scale=render_scale,
        scaled_width=source_width * render_scale,
        scaled_height=source_height * render_scale,
        crop_x=crop_x,
        crop_y=crop_y,
        crop_width=crop_width,
        crop_height=crop_height,
    )

