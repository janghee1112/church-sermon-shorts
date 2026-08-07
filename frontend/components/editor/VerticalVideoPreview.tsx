"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { formatTime } from "@/lib/time";
import { getTitleLayoutPreview, videoUrl } from "@/lib/api";
import { calculateVerticalCrop } from "@/lib/verticalCrop";
import { calculateLetterboxVideoArea, SERMON_LETTERBOX_TEMPLATE } from "@/lib/sermonTemplate";
import type { DraftSubtitle, DraftVisualSettings, TitleLayoutPreview } from "@/types";

const PREVIEW_WIDTH = SERMON_LETTERBOX_TEMPLATE.previewWidth;
const PREVIEW_HEIGHT = SERMON_LETTERBOX_TEMPLATE.previewHeight;

type PitchPreservingVideo = HTMLVideoElement & {
  webkitPreservesPitch?: boolean;
  mozPreservesPitch?: boolean;
};

function applyPlaybackRate(video: HTMLVideoElement, playbackRate: number) {
  const pitchVideo = video as PitchPreservingVideo;
  video.playbackRate = playbackRate;
  video.defaultPlaybackRate = playbackRate;
  video.preservesPitch = true;
  pitchVideo.webkitPreservesPitch = true;
  pitchVideo.mozPreservesPitch = true;
}

export interface VideoPreviewHandle {
  seekAndPlay: (seconds: number, endSec?: number) => void;
  restartRange: () => void;
}

interface Props {
  projectId: string;
  startSec: number;
  endSec: number;
  title: string;
  settings: DraftVisualSettings;
  subtitles: DraftSubtitle[];
  showSafeAreas: boolean;
  onTimeChange: (seconds: number) => void;
}

export const VerticalVideoPreview = forwardRef<VideoPreviewHandle, Props>(function VerticalVideoPreview(
  { projectId, startSec, endSec, title, settings, subtitles, showSafeAreas, onTimeChange },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const stopAtRef = useRef<number | null>(endSec);
  const titleRef = useRef<HTMLDivElement>(null);
  const subtitleRef = useRef<HTMLDivElement>(null);
  const videoRegionRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(startSec);
  const [playing, setPlaying] = useState(false);
  const [originalRatio, setOriginalRatio] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const [bannerFailed, setBannerFailed] = useState(false);
  const [textOverlap, setTextOverlap] = useState(false);
  const [subtitleVideoOverlap, setSubtitleVideoOverlap] = useState(false);
  const [titleLayoutState, setTitleLayoutState] = useState<{ key: string; value: TitleLayoutPreview } | null>(null);
  const activeCue = subtitles.find((cue) => currentTime >= cue.start_sec - 0.05 && currentTime < cue.end_sec + 0.05);
  const activeText = activeCue ? activeCue.edited_text || activeCue.original_text : "";
  const progress = Math.max(0, Math.min(100, ((currentTime - startSec) / Math.max(0.1, endSec - startSec)) * 100));
  const titleLayoutKey = JSON.stringify([
    title,
    settings.title_font_scale,
    settings.title_position_y,
    settings.title_highlight_ranges,
  ]);
  const titleLayout = titleLayoutState?.key === titleLayoutKey ? titleLayoutState.value : null;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    applyPlaybackRate(video, settings.playback_rate);
  }, [settings.playback_rate]);

  useEffect(() => {
    if (!title) {
      setTitleLayoutState(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void getTitleLayoutPreview(
        title,
        settings.title_font_scale,
        settings.title_position_y,
        settings.title_highlight_ranges,
        controller.signal,
      ).then((value) => {
        setTitleLayoutState({ key: titleLayoutKey, value });
      }).catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (process.env.NODE_ENV !== "production") console.warn("제목 레이아웃 미리보기를 불러오지 못했습니다.");
      });
    }, 120);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [title, titleLayoutKey, settings.title_font_scale, settings.title_position_y, settings.title_highlight_ranges]);

  function ensureCanvas(refValue: typeof sourceCanvasRef, width: number, height: number) {
    if (!refValue.current) {
      refValue.current = document.createElement("canvas");
    }
    if (refValue.current.width !== width) refValue.current.width = width;
    if (refValue.current.height !== height) refValue.current.height = height;
    return refValue.current;
  }

  const drawFrame = useCallback(() => {
    const video = videoRef.current;
    const output = canvasRef.current;
    if (!video || !output || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return;
    const videoArea = calculateLetterboxVideoArea(
      PREVIEW_WIDTH,
      PREVIEW_HEIGHT,
      settings.video_area_position_y,
      settings.video_area_height,
    );
    const videoAreaWidth = Math.max(1, Math.round(videoArea.width));
    const videoAreaHeight = Math.max(1, Math.round(videoArea.height));
    const videoAreaX = Math.round(videoArea.x);
    const videoAreaY = Math.round(videoArea.y);
    const source = ensureCanvas(sourceCanvasRef, videoAreaWidth, videoAreaHeight);
    const sourceContext = source.getContext("2d", { alpha: false });
    const outputContext = output.getContext("2d", { alpha: false });
    if (!sourceContext || !outputContext) return;
    const crop = calculateVerticalCrop({
      sourceWidth: video.videoWidth,
      sourceHeight: video.videoHeight,
      targetWidth: videoAreaWidth,
      targetHeight: videoAreaHeight,
      zoomScale: settings.zoom_scale,
      cropPositionX: settings.crop_position_x,
      cropPositionY: settings.crop_position_y,
    });
    sourceContext.clearRect(0, 0, videoAreaWidth, videoAreaHeight);
    sourceContext.drawImage(video, crop.cropX, crop.cropY, crop.cropWidth, crop.cropHeight, 0, 0, videoAreaWidth, videoAreaHeight);
    outputContext.save();
    outputContext.fillStyle = "#000000";
    outputContext.fillRect(0, 0, PREVIEW_WIDTH, PREVIEW_HEIGHT);
    outputContext.drawImage(source, videoAreaX, videoAreaY);
    outputContext.restore();
  }, [settings]);

  useEffect(() => {
    drawFrame();
  }, [drawFrame, activeText]);

  useEffect(() => {
    if (!playing) return;
    let animationFrame = 0;
    const render = () => {
      drawFrame();
      animationFrame = window.requestAnimationFrame(render);
    };
    animationFrame = window.requestAnimationFrame(render);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [playing, drawFrame]);

  useEffect(() => {
    const titleElement = titleRef.current;
    const subtitleElement = subtitleRef.current;
    const videoRegion = videoRegionRef.current;
    if (!subtitleElement || !videoRegion || !activeText) {
      setTextOverlap(false);
      setSubtitleVideoOverlap(false);
      return;
    }
    const subtitleBounds = subtitleElement.getBoundingClientRect();
    const videoBounds = videoRegion.getBoundingClientRect();
    setSubtitleVideoOverlap(subtitleBounds.height > 0 && videoBounds.height > 0 && subtitleBounds.bottom > videoBounds.top - 4);
    if (!titleElement) {
      setTextOverlap(false);
      return;
    }
    const titleBounds = titleElement.getBoundingClientRect();
    if (titleBounds.height === 0 || subtitleBounds.height === 0) {
      setTextOverlap(false);
      return;
    }
    setTextOverlap(titleBounds.bottom > subtitleBounds.top - 4);
  }, [title, titleLayout?.total_height_px, activeText, settings.title_font_scale, settings.title_position_y, settings.subtitle_font_scale, settings.subtitle_position_y, settings.video_area_position_y, settings.video_area_height]);

  function seekAndPlay(seconds: number, stopAt = endSec) {
    const video = videoRef.current;
    if (!video) return;
    stopAtRef.current = stopAt;
    video.currentTime = seconds;
    void video.play().catch(() => undefined);
  }

  useImperativeHandle(ref, () => ({
    seekAndPlay,
    restartRange: () => seekAndPlay(startSec, endSec),
  }), [startSec, endSec]);

  useEffect(() => {
    stopAtRef.current = endSec;
    const video = videoRef.current;
    if (video && (video.currentTime < startSec || video.currentTime > endSec)) video.currentTime = startSec;
  }, [startSec, endSec]);

  function updateTime() {
    const video = videoRef.current;
    if (!video) return;
    setCurrentTime(video.currentTime);
    onTimeChange(video.currentTime);
    const stopAt = stopAtRef.current;
    if (stopAt !== null && video.currentTime >= stopAt - 0.1) {
      video.pause();
      stopAtRef.current = null;
    }
  }

  function skip(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(startSec, Math.min(endSec, video.currentTime + seconds));
    stopAtRef.current = endSec;
  }

  return (
    <section aria-label="세로형 쇼츠 미리보기">
      <div
        data-testid="letterbox-canvas"
        className={`relative mx-auto overflow-hidden bg-black shadow-2xl ${originalRatio ? "aspect-video w-full rounded-2xl" : "aspect-[9/16] w-full rounded-[2rem]"}`}
        style={originalRatio ? undefined : { maxWidth: "min(390px, calc(56.25vh - 7.3125rem))" }}
      >
        <video
          ref={videoRef}
          data-testid="editor-video"
          src={videoUrl(projectId)}
          crossOrigin="anonymous"
          playsInline
          preload="metadata"
          className={originalRatio ? "h-full w-full object-contain" : "pointer-events-none absolute h-px w-px opacity-0"}
          onTimeUpdate={updateTime}
          onPlay={() => setPlaying(true)}
          onPause={() => { setPlaying(false); drawFrame(); }}
          onLoadedData={(event) => { event.currentTarget.currentTime = startSec; applyPlaybackRate(event.currentTarget, settings.playback_rate); drawFrame(); }}
          onSeeked={drawFrame}
          onError={() => setVideoError(true)}
        />
        {!originalRatio && <canvas ref={canvasRef} data-testid="composite-canvas" width={PREVIEW_WIDTH} height={PREVIEW_HEIGHT} className="h-full w-full" />}
        {videoError && <div role="alert" className="absolute inset-0 z-40 grid place-items-center bg-black/80 p-6 text-center text-sm font-bold text-white">원본 영상을 불러오지 못했습니다. 백엔드 서버와 영상 파일을 확인해 주세요.</div>}
        {!originalRatio && <>
          <div ref={videoRegionRef} data-testid="letterbox-video-region" className="pointer-events-none absolute inset-x-0 z-10" data-position-y={settings.video_area_position_y} data-height={settings.video_area_height} style={{ top: `${settings.video_area_position_y * 100}%`, height: `${settings.video_area_height * 100}%` }} />
          {titleLayout && <>
            <img
              data-testid="template-title"
              data-font-key={titleLayout.font_key}
              data-font-name={titleLayout.font_name}
              data-line-count={titleLayout.lines.length}
              data-effective-font-size={titleLayout.font_size_px}
              data-line-height={titleLayout.line_height_px}
              data-auto-fit={titleLayout.auto_fit_applied}
              src={titleLayout.image_data_url}
              alt=""
              aria-hidden="true"
              draggable={false}
              className="pointer-events-none absolute inset-0 z-20 h-full w-full select-none"
            />
            <div
              ref={titleRef}
              data-testid="template-title-bounds"
              className="pointer-events-none absolute z-20"
              style={{
                left: `${(titleLayout.area.x / titleLayout.canvas_width) * 100}%`,
                top: `${(titleLayout.area.y / titleLayout.canvas_height) * 100}%`,
                width: `${(titleLayout.area.width / titleLayout.canvas_width) * 100}%`,
                height: `${(titleLayout.total_height_px / titleLayout.canvas_height) * 100}%`,
              }}
            />
          </>}
          {activeText && <div ref={subtitleRef} data-font-key={SERMON_LETTERBOX_TEMPLATE.subtitleFontKey} data-testid="active-subtitle" className="template-subtitle pointer-events-none absolute inset-x-[6%] z-20 whitespace-pre-line text-center font-bold leading-snug text-white" style={{ top: `${settings.subtitle_position_y * 100}%`, fontSize: `${1.05 * settings.subtitle_font_scale}rem`, fontFamily: SERMON_LETTERBOX_TEMPLATE.subtitleFontFamily }}>{activeText}</div>}
          {SERMON_LETTERBOX_TEMPLATE.banner.enabled && !bannerFailed && <img
            data-testid="church-banner"
            data-asset-key={SERMON_LETTERBOX_TEMPLATE.banner.assetKey}
            src={SERMON_LETTERBOX_TEMPLATE.banner.assetPath}
            alt=""
            aria-hidden="true"
            draggable={false}
            width={SERMON_LETTERBOX_TEMPLATE.banner.sourceWidth}
            height={SERMON_LETTERBOX_TEMPLATE.banner.sourceHeight}
            className="pointer-events-none absolute z-20 h-auto select-none object-contain"
            style={{
              left: `${SERMON_LETTERBOX_TEMPLATE.banner.positionX * 100}%`,
              top: `${SERMON_LETTERBOX_TEMPLATE.banner.positionY * 100}%`,
              width: `${Number((SERMON_LETTERBOX_TEMPLATE.banner.widthRatio * 100).toFixed(2))}%`,
              transform: "translateX(-50%)",
            }}
            onError={() => {
              if (process.env.NODE_ENV !== "production") console.warn("교회 배너 이미지를 불러오지 못했습니다.");
              setBannerFailed(true);
            }}
          />}
          {showSafeAreas && <div data-testid="safe-area-guide" className="pointer-events-none absolute inset-x-[7%] bottom-[10%] top-[7%] z-30 border border-dashed border-yellow-300/60"><span className="absolute left-1 top-1 text-[9px] font-bold text-yellow-200/80">제목·대본 안전 영역</span><span className="absolute bottom-1 right-1 text-[9px] font-bold text-yellow-200/80">하단 UI 주의</span><div data-testid="video-area-guide" className="absolute -left-[7.5%] w-[115%] border-y border-cyan-300/70" style={{ top: `${((settings.video_area_position_y - 0.07) / 0.83) * 100}%`, height: `${(settings.video_area_height / 0.83) * 100}%` }}><span className="absolute left-2 top-1 text-[9px] font-bold text-cyan-200/90">가로 영상 영역</span></div></div>}
          {textOverlap && <div role="alert" className="absolute inset-x-4 top-1/2 z-30 rounded-lg bg-amber-500/90 px-3 py-2 text-center text-xs font-bold text-black">제목과 자막이 겹칠 수 있습니다.</div>}
          {subtitleVideoOverlap && <div role="alert" className="absolute inset-x-4 top-[84%] z-30 rounded-lg bg-amber-500/90 px-3 py-2 text-center text-xs font-bold text-black">대본이 영상 영역과 겹칠 수 있습니다.</div>}
        </>}
        <div className="absolute inset-x-0 bottom-0 z-30 h-1.5 bg-white/25"><div className="h-full bg-gold" style={{ width: `${progress}%` }} /></div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        <button type="button" onClick={() => seekAndPlay(startSec, endSec)} className="focus-ring rounded-lg bg-moss px-3 py-2 text-sm font-bold text-white">선택 구간 재생</button>
        <button type="button" onClick={() => skip(-5)} className="focus-ring rounded-lg bg-white px-3 py-2 text-sm font-bold">−5초</button>
        <button data-testid="preview-play-toggle" type="button" onClick={() => { const video = videoRef.current; if (!video) return; if (video.paused) seekAndPlay(video.currentTime < startSec || video.currentTime >= endSec ? startSec : video.currentTime); else video.pause(); }} className="focus-ring min-w-24 rounded-lg bg-ink px-4 py-2 text-sm font-bold text-white">{playing ? "일시정지" : "재생"}</button>
        <button type="button" onClick={() => skip(5)} className="focus-ring rounded-lg bg-white px-3 py-2 text-sm font-bold">+5초</button>
        <button type="button" onClick={() => seekAndPlay(startSec, endSec)} className="focus-ring rounded-lg bg-white px-3 py-2 text-sm font-bold">처음부터</button>
        <button type="button" onClick={() => setOriginalRatio((value) => !value)} className="focus-ring rounded-lg border border-moss/20 bg-mint px-3 py-2 text-sm font-bold text-moss">{originalRatio ? "9:16 보기" : "원본 비율"}</button>
      </div>
      <p className="mt-2 text-center font-mono text-xs text-ink/50">{formatTime(currentTime)} / {formatTime(endSec)} · 원본 구간 {formatTime(endSec - startSec)} · 예상 완성 길이 {formatTime((endSec - startSec) / settings.playback_rate)} ({settings.playback_rate.toFixed(1)}x)</p>
    </section>
  );
});
