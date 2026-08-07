export interface VerticalCropInput {
  sourceWidth: number;
  sourceHeight: number;
  targetWidth: number;
  targetHeight: number;
  zoomScale: number;
  cropPositionX: number;
  cropPositionY: number;
}

export interface VerticalCropResult {
  scaledWidth: number;
  scaledHeight: number;
  cropX: number;
  cropY: number;
  cropWidth: number;
  cropHeight: number;
}

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

/**
 * Calculates a source-space crop for a target aspect ratio.
 * The same six values can be translated directly into an FFmpeg crop/scale step.
 */
export function calculateVerticalCrop(input: VerticalCropInput): VerticalCropResult {
  const sourceWidth = Math.max(1, input.sourceWidth);
  const sourceHeight = Math.max(1, input.sourceHeight);
  const targetWidth = Math.max(1, input.targetWidth);
  const targetHeight = Math.max(1, input.targetHeight);
  const zoomScale = clamp(input.zoomScale, 1, 1.4);
  const coverScale = Math.max(targetWidth / sourceWidth, targetHeight / sourceHeight);
  const renderScale = coverScale * zoomScale;
  const cropWidth = targetWidth / renderScale;
  const cropHeight = targetHeight / renderScale;
  const cropX = (sourceWidth - cropWidth) * clamp(input.cropPositionX, 0, 1);
  const cropY = (sourceHeight - cropHeight) * clamp(input.cropPositionY, 0, 1);

  return {
    scaledWidth: sourceWidth * renderScale,
    scaledHeight: sourceHeight * renderScale,
    cropX,
    cropY,
    cropWidth,
    cropHeight,
  };
}
