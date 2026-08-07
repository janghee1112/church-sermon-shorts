from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.core.config import PROJECT_ROOT
from app.core.template_defaults import (
    SERMON_LETTERBOX_BANNER_POSITION_X,
    SERMON_LETTERBOX_BANNER_POSITION_Y,
    SERMON_LETTERBOX_BANNER_WIDTH_RATIO,
)


@dataclass(frozen=True)
class BannerAsset:
    enabled: bool
    asset_key: str
    path: Path
    width_ratio: float
    position_x: float
    position_y: float


@dataclass(frozen=True)
class BannerLayout:
    width: int
    height: int
    x: int
    y: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


SERMON_LETTERBOX_BANNER = BannerAsset(
    enabled=True,
    asset_key="onnuri_vision_church",
    path=PROJECT_ROOT / "backend" / "assets" / "church" / "onnuri-vision-banner.png",
    width_ratio=SERMON_LETTERBOX_BANNER_WIDTH_RATIO,
    position_x=SERMON_LETTERBOX_BANNER_POSITION_X,
    position_y=SERMON_LETTERBOX_BANNER_POSITION_Y,
)


def get_template_banner(template_type: str) -> BannerAsset:
    if template_type != "sermon_letterbox_v1":
        raise ValueError("지원하지 않는 쇼츠 템플릿입니다.")
    return SERMON_LETTERBOX_BANNER


def inspect_banner_asset(asset: BannerAsset) -> tuple[int, int]:
    if not asset.path.is_file():
        raise ValueError("교회 배너 이미지 파일을 찾을 수 없습니다.")
    with Image.open(asset.path) as image:
        if image.format != "PNG" or "A" not in image.getbands():
            raise ValueError("교회 배너 이미지는 투명 배경 PNG여야 합니다.")
        return image.width, image.height


def calculate_banner_layout(
    canvas_width: int,
    canvas_height: int,
    source_width: int,
    source_height: int,
    width_ratio: float,
    position_x: float,
    position_y: float,
) -> BannerLayout:
    if min(canvas_width, canvas_height, source_width, source_height) <= 0:
        raise ValueError("배너 크기 계산값이 올바르지 않습니다.")
    safe_width_ratio = min(0.88, max(0.01, width_ratio))
    width = round(canvas_width * safe_width_ratio)
    height = round(width * source_height / source_width)
    x = round((canvas_width - width) * min(1.0, max(0.0, position_x)))
    y = round(canvas_height * min(1.0, max(0.0, position_y)))
    layout = BannerLayout(width=width, height=height, x=x, y=y)
    horizontal_margin = round(canvas_width * 0.06)
    bottom_margin = round(canvas_height * 0.05)
    if layout.x < horizontal_margin or layout.right > canvas_width - horizontal_margin:
        raise ValueError("교회 배너가 좌우 안전 영역을 벗어납니다.")
    if layout.y < 0 or layout.bottom > canvas_height - bottom_margin:
        raise ValueError("교회 배너가 하단 안전 영역을 벗어납니다.")
    return layout
