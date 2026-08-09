"use client";

import { useEffect, useRef, useState } from "react";
import { SERMON_LETTERBOX_TEMPLATE } from "@/lib/sermonTemplate";
import type { DraftSubtitle, DraftVisualSettings } from "@/types";
import { TitleHighlightEditor } from "./TitleHighlightEditor";

export const DEFAULT_TEMPLATE_SETTINGS: Omit<DraftVisualSettings, "custom_title"> = {
  title_highlight_ranges: [],
  zoom_scale: SERMON_LETTERBOX_TEMPLATE.defaultZoomScale,
  crop_position_x: SERMON_LETTERBOX_TEMPLATE.defaultCropPositionX,
  crop_position_y: SERMON_LETTERBOX_TEMPLATE.defaultCropPositionY,
  video_area_position_y: SERMON_LETTERBOX_TEMPLATE.defaultVideoAreaPositionY,
  video_area_height: 0.48,
  title_font_scale: SERMON_LETTERBOX_TEMPLATE.defaultTitleFontScale,
  title_position_y: SERMON_LETTERBOX_TEMPLATE.defaultTitlePositionY,
  subtitle_font_scale: SERMON_LETTERBOX_TEMPLATE.defaultSubtitleFontScale,
  subtitle_position_y: SERMON_LETTERBOX_TEMPLATE.defaultSubtitlePositionY,
  playback_rate: SERMON_LETTERBOX_TEMPLATE.defaultPlaybackRate,
  template_type: "sermon_letterbox_v1",
};

export const LETTERBOX_COMPOSITION_RESET = {
  zoom_scale: SERMON_LETTERBOX_TEMPLATE.defaultZoomScale,
  crop_position_x: SERMON_LETTERBOX_TEMPLATE.defaultCropPositionX,
  crop_position_y: SERMON_LETTERBOX_TEMPLATE.defaultCropPositionY,
  video_area_position_y: SERMON_LETTERBOX_TEMPLATE.defaultVideoAreaPositionY,
  video_area_height: 0.48,
} as const;

interface Props {
  settings: DraftVisualSettings;
  currentSubtitle: DraftSubtitle | null;
  showSafeAreas: boolean;
  onShowSafeAreasChange: (value: boolean) => void;
  onChange: (values: Partial<DraftVisualSettings>) => void;
}

function Slider({ label, value, minimum, maximum, step, display, onChange }: { label: string; value: number; minimum: number; maximum: number; step: number; display: string; onChange: (value: number) => void }) {
  return <label className="block"><span className="flex items-center justify-between text-xs font-bold text-ink/60"><span>{label}</span><span>{display}</span></span><input aria-label={label} type="range" min={minimum} max={maximum} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} className="mt-2 w-full accent-[#315f4b]" /></label>;
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl bg-cream/70 px-3 py-2.5 text-sm font-bold"><span>{label}</span><input aria-label={label} type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="h-5 w-5 accent-[#315f4b]" /></label>;
}

export function TemplateSettingsPanel({ settings, currentSubtitle, showSafeAreas, onShowSafeAreasChange, onChange }: Props) {
  const [highlightResetNotice, setHighlightResetNotice] = useState(false);
  const initialTitlePositionRef = useRef(Math.max(SERMON_LETTERBOX_TEMPLATE.titlePositionMin, settings.title_position_y));
  const titlePositionMinimum = initialTitlePositionRef.current;
  const titlePositionMaximum = Math.max(titlePositionMinimum, SERMON_LETTERBOX_TEMPLATE.titlePositionMax);
  const titleLines = settings.custom_title ? settings.custom_title.split("\n").length : 0;
  const subtitleText = currentSubtitle ? currentSubtitle.edited_text || currentSubtitle.original_text : "";
  const subtitleLines = subtitleText ? subtitleText.split("\n").length : 0;

  useEffect(() => {
    if (!highlightResetNotice) return;
    const timer = window.setTimeout(() => setHighlightResetNotice(false), 3000);
    return () => window.clearTimeout(timer);
  }, [highlightResetNotice]);

  function changeTitle(nextTitle: string) {
    if (nextTitle === settings.custom_title) return;
    const hadHighlights = settings.title_highlight_ranges.length > 0;
    onChange({ custom_title: nextTitle, title_highlight_ranges: [] });
    if (hadHighlights) setHighlightResetNotice(true);
  }

  return <div className="space-y-5">
    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div className="flex items-start justify-between gap-3"><div><p className="text-[11px] font-black tracking-[.16em] text-gold">1 · TITLE</p><h2 className="serif mt-1 text-xl font-bold">제목</h2></div><span className="text-xs text-ink/40">{settings.custom_title.length}/60</span></div>
      <textarea aria-label="쇼츠 큰 제목" maxLength={60} rows={2} value={settings.custom_title} placeholder="비워두면 제목 영역도 비워집니다" onChange={(event) => changeTitle(event.target.value)} className="template-title-editor focus-ring mt-3 w-full resize-y rounded-xl border border-ink/10 bg-cream/60 px-4 py-3 text-lg" />
      {titleLines > 2 && <p className="mt-1 text-xs font-bold text-amber-700">제목이 세 줄 이상입니다. 두 줄 이내를 권장합니다.</p>}
      {highlightResetNotice && <p role="status" className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">제목이 변경되어 기존 강조 선택이 초기화되었습니다.</p>}
      <TitleHighlightEditor title={settings.custom_title} ranges={settings.title_highlight_ranges} onChange={(title_highlight_ranges) => onChange({ title_highlight_ranges })} />
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Slider label="제목 글자 크기" value={settings.title_font_scale} minimum={0.7} maximum={1.5} step={0.01} display={`${Math.round(settings.title_font_scale * 100)}%`} onChange={(value) => onChange({ title_font_scale: value })} />
        <Slider label="제목 아래로 내리기" value={settings.title_position_y} minimum={titlePositionMinimum} maximum={titlePositionMaximum} step={0.01} display={settings.title_position_y <= titlePositionMinimum ? "현재 위치" : `아래 ${Math.round(((settings.title_position_y - titlePositionMinimum) / (titlePositionMaximum - titlePositionMinimum)) * 100)}%`} onChange={(value) => onChange({ title_position_y: value })} />
      </div>
    </section>

    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div><p className="text-[11px] font-black tracking-[.16em] text-gold">2 · VIDEO POSITION</p><h2 className="serif mt-1 text-xl font-bold">영상 위치</h2><p className="mt-1 text-xs text-ink/45">영상은 검은 캔버스 안의 독립된 가로 영역에 배치됩니다.</p></div>
      <div className="mt-4 space-y-4">
        <Slider label="영상 확대" value={settings.zoom_scale} minimum={1} maximum={1.4} step={0.01} display={`${Math.round(settings.zoom_scale * 100)}%`} onChange={(value) => onChange({ zoom_scale: value })} />
        <Slider label="영상 가로 위치" value={settings.crop_position_x} minimum={0} maximum={1} step={0.01} display={`${Math.round(settings.crop_position_x * 100)}%`} onChange={(value) => onChange({ crop_position_x: value })} />
        <Slider label="영상 세로 위치" value={settings.crop_position_y} minimum={0} maximum={1} step={0.01} display={`${Math.round(settings.crop_position_y * 100)}%`} onChange={(value) => onChange({ crop_position_y: value })} />
        <Slider label="영상 영역 위아래 위치" value={settings.video_area_position_y} minimum={SERMON_LETTERBOX_TEMPLATE.videoAreaPositionMin} maximum={SERMON_LETTERBOX_TEMPLATE.videoAreaPositionMax} step={0.01} display={`${Math.round(settings.video_area_position_y * 100)}%`} onChange={(value) => onChange({ video_area_position_y: value })} />
        <fieldset><legend className="text-xs font-bold text-ink/60">재생 속도</legend><div className="mt-2 grid grid-cols-5 gap-2">{[0.9, 1, 1.1, 1.2, 1.3].map((rate) => <button key={rate} type="button" aria-pressed={settings.playback_rate === rate} onClick={() => onChange({ playback_rate: rate })} className={`focus-ring rounded-lg px-2 py-2 text-xs font-black ${settings.playback_rate === rate ? "bg-moss text-white" : "border border-ink/10 bg-cream text-ink"}`}>{rate.toFixed(1)}x</button>)}</div></fieldset>
      </div>
      <button type="button" onClick={() => onChange(LETTERBOX_COMPOSITION_RESET)} className="focus-ring mt-4 w-full rounded-lg border border-ink/10 bg-cream px-3 py-2 text-xs font-bold">영상 위치 초기화</button>
    </section>

    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div><p className="text-[11px] font-black tracking-[.16em] text-gold">3 · SUBTITLE</p><h2 className="serif mt-1 text-xl font-bold">자막</h2></div>
      <div className="template-subtitle mt-3 min-h-16 rounded-xl bg-black px-4 py-3 text-center text-sm font-bold leading-6 text-white">{subtitleText || "재생 시간에 해당하는 실제 대본이 여기에 표시됩니다."}</div>
      {subtitleLines > 2 && <p className="mt-2 text-xs font-bold text-amber-700">자막이 세 줄 이상입니다. 영상 영역과 겹치지 않는지 확인해 주세요.</p>}
      <div className="mt-4 grid gap-4 sm:grid-cols-2"><Slider label="자막 글자 크기" value={settings.subtitle_font_scale} minimum={0.7} maximum={1.5} step={0.01} display={`${Math.round(settings.subtitle_font_scale * 100)}%`} onChange={(value) => onChange({ subtitle_font_scale: value })} /><Slider label="자막 위치" value={settings.subtitle_position_y} minimum={0.18} maximum={0.5} step={0.01} display={`${Math.round(settings.subtitle_position_y * 100)}%`} onChange={(value) => onChange({ subtitle_position_y: value })} /></div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2"><a href="#subtitle-editor" className="focus-ring inline-block rounded-lg bg-mint px-3 py-2 text-xs font-bold text-moss">자막 편집 목록으로 이동</a><Toggle label="안전 영역 보기" checked={showSafeAreas} onChange={onShowSafeAreasChange} /></div>
    </section>
  </div>;
}
