export const SERMON_LETTERBOX_TEMPLATE = {
  type: "sermon_letterbox_v1",
  titleFontKey: "pretendard_black_v1",
  titleFontFamily: "var(--sermon-title-font)",
  subtitleFontKey: "korean_gothic_v1",
  subtitleFontFamily: "var(--sermon-subtitle-font)",
  titleHighlightColorVar: "--sermon-highlight",
  previewWidth: 360,
  previewHeight: 640,
  defaultZoomScale: 1.3,
  defaultCropPositionX: 0.5,
  defaultCropPositionY: 0.70,
  defaultTitleFontScale: 1.0,
  defaultTitlePositionY: 0.08,
  titlePositionMin: 0.08,
  titlePositionMax: 0.2,
  defaultSubtitleFontScale: 0.9,
  defaultSubtitlePositionY: 0.52,
  subtitlePositionMax: 0.790625,
  defaultVideoAreaPositionY: 0.28,
  videoAreaPositionMin: 0.22,
  videoAreaPositionMax: 0.34,
  defaultVideoAreaHeight: 0.48,
  defaultPlaybackRate: 1.2,
  fadeOutDuration: 1,
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

export function calculatePreviewFadeOpacity(
  currentTime: number,
  startSec: number,
  endSec: number,
  playbackRate: number,
  fadeDuration = SERMON_LETTERBOX_TEMPLATE.fadeOutDuration,
): number {
  const safePlaybackRate = playbackRate > 0 ? playbackRate : 1;
  const outputDuration = Math.max(0, (endSec - startSec) / safePlaybackRate);
  if (outputDuration <= 0) return 1;
  const effectiveFadeDuration = Math.min(outputDuration, Math.max(0, fadeDuration));
  if (effectiveFadeDuration <= 0) return 0;
  const outputElapsed = Math.min(outputDuration, Math.max(0, currentTime - startSec) / safePlaybackRate);
  const outputRemaining = outputDuration - outputElapsed;
  return Math.min(1, Math.max(0, 1 - outputRemaining / effectiveFadeDuration));
}

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
