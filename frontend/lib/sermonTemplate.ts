export const SERMON_LETTERBOX_TEMPLATE = {
  type: "sermon_letterbox_v1",
  titleFontKey: "pretendard_black_v1",
  titleFontFamily: "var(--sermon-title-font)",
  subtitleFontKey: "korean_myeongjo_v1",
  subtitleFontFamily: "var(--sermon-subtitle-font)",
  titleHighlightColorVar: "--sermon-highlight",
  previewWidth: 360,
  previewHeight: 640,
  defaultZoomScale: 1.3,
  defaultCropPositionX: 0.5,
  defaultCropPositionY: 0.42,
  defaultTitleFontScale: 1.2,
  defaultTitlePositionY: 0.08,
  titlePositionMin: 0.08,
  titlePositionMax: 0.2,
  defaultSubtitleFontScale: 1,
  defaultSubtitlePositionY: 0.24,
  defaultVideoAreaPositionY: 0.28,
  videoAreaPositionMin: 0.22,
  videoAreaPositionMax: 0.34,
  defaultVideoAreaHeight: 0.48,
  defaultPlaybackRate: 1.2,
  bottomSafetyRatio: 0.1,
  banner: {
    enabled: true,
    assetKey: "onnuri_vision_church",
    assetPath: "/assets/church/onnuri-vision-banner.png",
    sourceWidth: 1799,
    sourceHeight: 361,
    widthRatio: 0.368,
    positionX: 0.5,
    positionY: 0.790625,
  },
} as const;

export type SermonTemplateType = typeof SERMON_LETTERBOX_TEMPLATE.type;

export function calculateLetterboxVideoArea(
  canvasWidth: number,
  canvasHeight: number,
  positionY: number,
  heightRatio: number,
) {
  const safeHeight = Math.min(0.58, Math.max(0.38, heightRatio));
  const safePositionY = Math.min(1 - safeHeight, Math.max(0, positionY));
  const height = Math.min(canvasHeight - safePositionY * canvasHeight, safeHeight * canvasHeight);
  return {
    x: 0,
    y: safePositionY * canvasHeight,
    width: canvasWidth,
    height,
  };
}
