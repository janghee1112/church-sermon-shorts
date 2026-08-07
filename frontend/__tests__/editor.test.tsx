import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CandidateEditButton } from "@/components/CandidateEditButton";
import { SubtitleEditor } from "@/components/editor/SubtitleEditor";
import { TranscriptRangeSelector } from "@/components/editor/TranscriptRangeSelector";
import { VerticalVideoPreview, type VideoPreviewHandle } from "@/components/editor/VerticalVideoPreview";
import { HighlightedTitle } from "@/components/editor/HighlightedTitle";
import { DEFAULT_TEMPLATE_SETTINGS, LETTERBOX_COMPOSITION_RESET, TemplateSettingsPanel } from "@/components/editor/TemplateSettingsPanel";
import { ShortsEditorPage } from "@/components/editor/ShortsEditorPage";
import { RenderPanel } from "@/components/editor/RenderPanel";
import { createDraft, createRender, getDraft, getDraftRenders, getTitleLayoutPreview, getTranscript, saveDraftSubtitles, updateDraft } from "@/lib/api";
import { calculateVerticalCrop } from "@/lib/verticalCrop";
import { calculateLetterboxVideoArea, SERMON_LETTERBOX_TEMPLATE } from "@/lib/sermonTemplate";
import type { ClipDraft, DraftSubtitle, DraftVisualSettings, RenderJob, TitleLayoutPreview, Transcript, TranscriptSegment } from "@/types";
import { createRef } from "react";

const push = vi.fn();
const apiMocks = vi.hoisted(() => ({
  createDraft: vi.fn(),
  getDraft: vi.fn(),
  getTranscript: vi.fn(),
  updateDraft: vi.fn(),
  saveDraftSubtitles: vi.fn(),
  createRender: vi.fn(),
  getRender: vi.fn(),
  getDraftRenders: vi.fn(),
  getTitleLayoutPreview: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, back: vi.fn() }) }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, ...apiMocks };
});
const subtitles: DraftSubtitle[] = [
  { id: 1, cue_order: 1, start_sec: 10, end_sec: 12, relative_start_sec: 0, relative_end_sec: 2, original_text: "원래 자막입니다", edited_text: "원래 자막입니다", is_edited: false },
  { id: 2, cue_order: 2, start_sec: 12, end_sec: 15, relative_start_sec: 2, relative_end_sec: 5, original_text: "두 번째 자막입니다", edited_text: "두 번째 자막입니다", is_edited: false },
];

const visualSettings: DraftVisualSettings = {
  custom_title: "큰 제목",
  title_highlight_ranges: [{ start: 2, end: 4 }],
  zoom_scale: 1.12,
  crop_position_x: 0.25,
  crop_position_y: 0.5,
  video_area_position_y: 0.34,
  video_area_height: 0.48,
  title_font_scale: 1,
  title_position_y: 0.11,
  subtitle_font_scale: 1,
  subtitle_position_y: 0.25,
  playback_rate: 1,
  template_type: "sermon_letterbox_v1",
};

const transcriptFixture: Transcript = {
  project_id: "p1",
  full_text: "원래 자막입니다 두 번째 자막입니다",
  segments: [
    { id: 11, segment_order: 1, start_sec: 10, end_sec: 12, text: "원래 자막입니다", words: [] },
    { id: 12, segment_order: 2, start_sec: 12, end_sec: 15, text: "두 번째 자막입니다", words: [] },
  ],
};

const draftFixture: ClipDraft = {
  id: 17,
  project_id: "p1",
  project_original_file_name: "sermon.mp4",
  analysis_mode: "real",
  candidate_id: 9,
  candidate: {
    id: 9,
    candidate_order: 1,
    main_topic: "믿음",
    recommended_start_segment_id: 11,
    recommended_end_segment_id: 12,
    recommended_start_sec: 10,
    recommended_end_sec: 15,
    title_placeholder: "추천 제목",
  },
  range: { start_segment_id: 11, end_segment_id: 12, start_sec: 10, end_sec: 15, duration_sec: 5 },
  title_highlight_text: "제목",
  ...visualSettings,
  status: "editing",
  subtitles,
  updated_at: "2026-08-04T08:00:00Z",
};

function titleLayoutFixture(title: string): TitleLayoutPreview {
  const lines = title.split("\n");
  return {
    canvas_width: 1080,
    canvas_height: 1920,
    initial_font_size_px: 84,
    font_size_px: 84,
    line_height_px: 91,
    total_height_px: lines.length * 91,
    auto_fit_applied: false,
    character_wrap_applied: false,
    area: { x: 76, y: 211, width: 929, height: 442 },
    lines: lines.map((text, index) => ({
      text,
      source_start: index === 0 ? 0 : lines.slice(0, index).join("\n").length + 1,
      source_end: (index === 0 ? 0 : lines.slice(0, index).join("\n").length + 1) + text.length,
      width_px: text.length * 70,
    })),
    font_key: "pretendard_black_v1",
    font_name: "Pretendard Black",
    image_data_url: "data:image/png;base64,dGl0bGU=",
  };
}

beforeEach(() => {
  push.mockReset();
  Object.values(apiMocks).forEach((mock) => mock.mockReset());
  apiMocks.getDraftRenders.mockResolvedValue([]);
  apiMocks.getTitleLayoutPreview.mockImplementation((title: string) => Promise.resolve(titleLayoutFixture(title)));
});

it("opens the editor only through the dedicated candidate edit button", async () => {
  vi.mocked(createDraft).mockResolvedValue({ id: 17 } as never);
  render(<CandidateEditButton projectId="project-1" candidateId={9} selectedTitleOrder={3} />);
  await userEvent.click(screen.getByRole("button", { name: "이 후보 편집하기" }));
  expect(createDraft).toHaveBeenCalledWith("project-1", 9, 3);
  await waitFor(() => expect(push).toHaveBeenCalledWith("/editor/17"));
});

it("selects transcript boundaries and applies the pending range", async () => {
  const segments: TranscriptSegment[] = [1, 2, 3].map((id) => ({ id, segment_order: id, start_sec: id * 10, end_sec: id * 10 + 10, text: `문장 ${id}`, words: [] }));
  const onChange = vi.fn();
  const onApply = vi.fn();
  render(<TranscriptRangeSelector segments={segments} pendingStartId={1} pendingEndId={2} recommendedStartId={1} recommendedEndId={2} activeSegmentId={2} onChange={onChange} onApply={onApply} onPlay={vi.fn()} />);
  await userEvent.click(screen.getAllByRole("button", { name: "종료로 설정" })[2]);
  expect(onChange).toHaveBeenCalledWith(1, 3);
  await userEvent.click(screen.getByRole("button", { name: "변경한 구간 적용" }));
  expect(onApply).toHaveBeenCalled();
});

it("edits, restores, splits, merges, and highlights subtitle rows", async () => {
  const onChange = vi.fn();
  const onSplit = vi.fn().mockResolvedValue(undefined);
  const onMerge = vi.fn().mockResolvedValue(undefined);
  const onResetOne = vi.fn();
  render(<SubtitleEditor subtitles={[{ ...subtitles[0], is_edited: true } as DraftSubtitle, subtitles[1]]} activeSubtitleId={1} onChange={onChange} onPlay={vi.fn()} onSplit={onSplit} onMerge={onMerge} onResetOne={onResetOne} onResetAll={vi.fn()} />);
  expect(screen.getByTestId("subtitle-1")).toHaveClass("border-gold");
  fireEvent.change(screen.getByLabelText("자막 1 편집"), { target: { value: "편집 문구" } });
  expect(onChange).toHaveBeenCalledWith(1, "편집 문구");
  await userEvent.click(screen.getAllByRole("button", { name: "자막 나누기" })[0]);
  await userEvent.click(screen.getByRole("button", { name: "이 위치에서 나누기" }));
  expect(onSplit).toHaveBeenCalled();
  await userEvent.click(screen.getAllByRole("button", { name: "다음과 합치기" })[0]);
  expect(onMerge).toHaveBeenCalledWith(1, 2);
  await userEvent.click(screen.getAllByRole("button", { name: "이 자막 원문 복원" })[0]);
  expect(onResetOne).toHaveBeenCalledWith(1);
});

it("syncs active subtitle and stops video at the selected end", async () => {
  const onTimeChange = vi.fn();
  const ref = createRef<VideoPreviewHandle>();
  render(<VerticalVideoPreview ref={ref} projectId="p1" startSec={10} endSec={15} title="큰 제목" settings={visualSettings} subtitles={subtitles} showSafeAreas onTimeChange={onTimeChange} />);
  const video = screen.getByTestId("editor-video") as HTMLVideoElement;
  ref.current?.seekAndPlay(10, 12);
  expect(video.currentTime).toBe(10);
  Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 10.5 });
  fireEvent.timeUpdate(video);
  expect(screen.getByTestId("active-subtitle")).toHaveTextContent("원래 자막입니다");
  expect(onTimeChange).toHaveBeenCalledWith(10.5);
  expect(screen.getByTestId("safe-area-guide")).toBeInTheDocument();
  expect(screen.getByTestId("letterbox-canvas")).toHaveClass("bg-black", "aspect-[9/16]");
  expect(screen.getByTestId("letterbox-video-region")).toHaveAttribute("data-position-y", "0.34");
  expect(screen.getByTestId("letterbox-video-region")).toHaveAttribute("data-height", "0.48");
  expect(screen.getByTestId("video-area-guide")).toBeInTheDocument();
  expect(screen.getByTestId("active-subtitle")).toHaveClass("template-subtitle");
  expect(screen.getByTestId("active-subtitle")).toHaveAttribute("data-font-key", "korean_myeongjo_v1");
  expect(await screen.findByTestId("template-title")).toHaveAttribute("data-font-key", "pretendard_black_v1");
  expect(Number.parseFloat(screen.getByTestId("template-title-bounds").style.top)).toBeLessThan(Number.parseFloat(screen.getByTestId("letterbox-video-region").style.top));
  expect(Number.parseFloat(screen.getByTestId("active-subtitle").style.top)).toBeLessThan(Number.parseFloat(screen.getByTestId("letterbox-video-region").style.top));
  video.currentTime = 11.95;
  fireEvent.timeUpdate(video);
  expect(video.pause).toHaveBeenCalled();
});

it("applies playback rate immediately while keeping original cue time comparisons", async () => {
  const accelerated = { ...visualSettings, playback_rate: 1.2 };
  render(<VerticalVideoPreview projectId="p1" startSec={10} endSec={15} title="큰 제목" settings={accelerated} subtitles={subtitles} showSafeAreas onTimeChange={vi.fn()} />);
  const video = screen.getByTestId("editor-video") as HTMLVideoElement;
  await waitFor(() => expect(video.playbackRate).toBe(1.2));
  expect(video.defaultPlaybackRate).toBe(1.2);
  expect(video.preservesPitch).toBe(true);
  video.currentTime = 12.5;
  fireEvent.timeUpdate(video);
  expect(screen.getByTestId("active-subtitle")).toHaveTextContent("두 번째 자막입니다");
  expect(screen.getByText(/예상 완성 길이 00:04 \(1.2x\)/)).toBeInTheDocument();
});

it("uses the canonical server title layout without browser re-wrapping", async () => {
  const title = "자족하려면 눈높이를\n낮추라고요?\n큰 오해입니다";
  const canonical = titleLayoutFixture(title);
  vi.mocked(getTitleLayoutPreview).mockResolvedValue(canonical);
  render(<VerticalVideoPreview projectId="p1" startSec={10} endSec={15} title={title} settings={visualSettings} subtitles={subtitles} showSafeAreas onTimeChange={vi.fn()} />);
  const layer = await screen.findByTestId("template-title");
  expect(getTitleLayoutPreview).toHaveBeenCalledWith(title, 1, 0.11, visualSettings.title_highlight_ranges, expect.any(AbortSignal));
  expect(layer).toHaveAttribute("data-line-count", "3");
  expect(layer).toHaveAttribute("data-effective-font-size", "84");
  expect(layer).toHaveAttribute("data-line-height", "91");
  expect(layer).toHaveAttribute("src", canonical.image_data_url);
  expect(Number.parseFloat(screen.getByTestId("template-title-bounds").style.width)).toBeCloseTo((929 / 1080) * 100);
});

it("places the church banner centered inside the lower black safe area without changing its ratio", () => {
  render(<VerticalVideoPreview projectId="p1" startSec={10} endSec={15} title="큰 제목" settings={visualSettings} subtitles={subtitles} showSafeAreas onTimeChange={vi.fn()} />);
  const banner = screen.getByTestId("church-banner") as HTMLImageElement;
  const config = SERMON_LETTERBOX_TEMPLATE.banner;
  const bannerWidth = SERMON_LETTERBOX_TEMPLATE.previewWidth * config.widthRatio;
  const bannerHeight = bannerWidth * config.sourceHeight / config.sourceWidth;
  const bannerTop = SERMON_LETTERBOX_TEMPLATE.previewHeight * config.positionY;
  const videoBottom = SERMON_LETTERBOX_TEMPLATE.previewHeight * (visualSettings.video_area_position_y + visualSettings.video_area_height);
  expect(banner).toHaveAttribute("src", config.assetPath);
  expect(banner).toHaveAttribute("width", String(config.sourceWidth));
  expect(banner).toHaveAttribute("height", String(config.sourceHeight));
  expect(banner).toHaveClass("h-auto", "object-contain", "pointer-events-none", "select-none");
  expect(banner.style.left).toBe("50%");
  expect(banner.style.transform).toBe("translateX(-50%)");
  expect(banner.style.width).toBe("46%");
  expect(banner.style.top).toBe("83%");
  expect(bannerTop).toBeGreaterThan(videoBottom);
  expect(bannerTop).toBeGreaterThan(SERMON_LETTERBOX_TEMPLATE.previewHeight * visualSettings.subtitle_position_y);
  expect(bannerTop + bannerHeight).toBeLessThan(SERMON_LETTERBOX_TEMPLATE.previewHeight * 0.95);
  expect((SERMON_LETTERBOX_TEMPLATE.previewWidth - bannerWidth) / 2 + bannerWidth / 2).toBe(180);
});

it("keeps the preview usable when the church banner fails to load", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  render(<VerticalVideoPreview projectId="p1" startSec={10} endSec={15} title="큰 제목" settings={visualSettings} subtitles={subtitles} showSafeAreas onTimeChange={vi.fn()} />);
  fireEvent.error(screen.getByTestId("church-banner"));
  expect(screen.queryByTestId("church-banner")).not.toBeInTheDocument();
  expect(screen.getByTestId("composite-canvas")).toBeInTheDocument();
  expect(warn).toHaveBeenCalledWith("교회 배너 이미지를 불러오지 못했습니다.");
  warn.mockRestore();
});

it("highlights position-based title ranges and preserves line breaks safely", () => {
  const { container } = render(<div className="whitespace-pre-wrap"><HighlightedTitle title={"하나님을\n움직이시게 하는 사람"} ranges={[{ start: 5, end: 11 }]} /></div>);
  expect(screen.getByTestId("title-highlight")).toHaveTextContent("움직이시게");
  expect(container.textContent).toBe("하나님을\n움직이시게 하는 사람");
});

it("renders the whole title in white when highlight text is absent", () => {
  render(<div data-testid="plain-title"><HighlightedTitle title="믿음으로 사는 사람" ranges={[]} /></div>);
  expect(screen.queryByTestId("title-highlight")).not.toBeInTheDocument();
  expect(screen.getByTestId("plain-title")).toHaveTextContent("믿음으로 사는 사람");
});

it("leaves the title area empty when the user has not entered a title", () => {
  render(<VerticalVideoPreview projectId="p1" startSec={10} endSec={15} title="" settings={visualSettings} subtitles={subtitles} showSafeAreas onTimeChange={vi.fn()} />);
  expect(screen.queryByTestId("template-title")).not.toBeInTheDocument();
  expect(screen.getByTestId("active-subtitle")).toBeInTheDocument();
});

it("calculates a bounded landscape crop inside the independent video area", () => {
  const videoArea = calculateLetterboxVideoArea(360, 640, 0.34, 0.48);
  const crop = calculateVerticalCrop({ sourceWidth: 1920, sourceHeight: 1080, targetWidth: videoArea.width, targetHeight: videoArea.height, zoomScale: 1.12, cropPositionX: 0.25, cropPositionY: 0.5 });
  expect(videoArea.y).toBeCloseTo(217.6);
  expect(videoArea.height).toBeCloseTo(307.2);
  expect(videoArea.height).toBeLessThan(640);
  expect(crop.cropWidth).toBeLessThan(1920);
  expect(crop.cropHeight).toBeLessThan(1080);
  expect(crop.cropX).toBeGreaterThanOrEqual(0);
  expect(crop.cropY).toBeGreaterThanOrEqual(0);
  expect(crop.cropX + crop.cropWidth).toBeLessThanOrEqual(1920);
  expect(crop.cropY + crop.cropHeight).toBeLessThanOrEqual(1080);
});

it("removes video darkness and resets every video position value", async () => {
  const onChange = vi.fn();
  const onShowSafeAreasChange = vi.fn();
  render(<TemplateSettingsPanel settings={visualSettings} currentSubtitle={subtitles[0]} showSafeAreas onShowSafeAreasChange={onShowSafeAreasChange} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "영상 위치 초기화" }));
  expect(onChange).toHaveBeenCalledWith(LETTERBOX_COMPOSITION_RESET);
  await userEvent.click(screen.getByLabelText("안전 영역 보기"));
  expect(onShowSafeAreasChange).toHaveBeenCalledWith(false);
  expect(screen.queryByText("배경")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("인물 분리 배경 어둡게")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("영상 어둡기")).not.toBeInTheDocument();
  expect(LETTERBOX_COMPOSITION_RESET).toEqual({
    zoom_scale: 1,
    crop_position_x: 0.5,
    crop_position_y: 0.5,
    video_area_position_y: 0.3,
    video_area_height: 0.48,
  });
  expect(screen.queryByText("고급 설정")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("인물 밝기")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("마스크 경계 부드러움")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("마스크 민감도")).not.toBeInTheDocument();
});

it("uses the raised sermon letterbox defaults without changing saved draft values", () => {
  expect(DEFAULT_TEMPLATE_SETTINGS.video_area_position_y).toBe(0.3);
  expect(DEFAULT_TEMPLATE_SETTINGS.title_position_y).toBe(0.08);
  expect(DEFAULT_TEMPLATE_SETTINGS.subtitle_position_y).toBe(0.21);
  expect(SERMON_LETTERBOX_TEMPLATE.banner.positionY).toBe(0.83);
  expect(SERMON_LETTERBOX_TEMPLATE.banner.widthRatio).toBe(0.46);
  expect(visualSettings.video_area_position_y).toBe(0.34);
  expect(visualSettings.title_position_y).toBe(0.11);
  expect(visualSettings.subtitle_position_y).toBe(0.25);
});

it("updates title and visual sliders with exact template values", () => {
  const onChange = vi.fn();
  render(<TemplateSettingsPanel settings={visualSettings} currentSubtitle={subtitles[0]} showSafeAreas onShowSafeAreasChange={vi.fn()} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("쇼츠 큰 제목"), { target: { value: "하나님을\n움직이시게 하는 사람" } });
  fireEvent.change(screen.getByLabelText("영상 확대"), { target: { value: "1.3" } });
  fireEvent.change(screen.getByLabelText("영상 가로 위치"), { target: { value: "0.7" } });
  fireEvent.change(screen.getByLabelText("영상 세로 위치"), { target: { value: "0.3" } });
  fireEvent.change(screen.getByLabelText("영상 영역 위아래 위치"), { target: { value: "0.4" } });
  expect(onChange).toHaveBeenCalledWith({ custom_title: "하나님을\n움직이시게 하는 사람", title_highlight_ranges: [] });
  expect(onChange).toHaveBeenCalledWith({ zoom_scale: 1.3 });
  expect(onChange).toHaveBeenCalledWith({ crop_position_x: 0.7 });
  expect(onChange).toHaveBeenCalledWith({ crop_position_y: 0.3 });
  expect(onChange).toHaveBeenCalledWith({ video_area_position_y: 0.4 });
});

it("shows simple playback presets and keeps position reset independent", async () => {
  const onChange = vi.fn();
  render(<TemplateSettingsPanel settings={visualSettings} currentSubtitle={subtitles[0]} showSafeAreas onShowSafeAreasChange={vi.fn()} onChange={onChange} />);
  expect(screen.getByRole("button", { name: "1.0x" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "1.2x" }));
  expect(onChange).toHaveBeenCalledWith({ playback_rate: 1.2 });
  await userEvent.click(screen.getByRole("button", { name: "영상 위치 초기화" }));
  expect(LETTERBOX_COMPOSITION_RESET).not.toHaveProperty("playback_rate");
});

const completedRender: RenderJob = {
  id: 31, project_id: "p1", draft_id: 17, version: 2, status: "completed", progress: 100,
  current_step: "finalizing", error_code: null, error_message: null,
  output_file_name: "short.mp4", output_file_size: 2_000_000, output_duration_sec: 5,
  output_width: 1080, output_height: 1920, preview_url: "/api/renders/31/video",
  download_url: "/api/renders/31/download", created_at: "2026-08-05T10:00:00Z",
  started_at: "2026-08-05T10:00:01Z", completed_at: "2026-08-05T10:01:00Z", updated_at: "2026-08-05T10:01:00Z",
};

it("starts one render and prevents a duplicate click while it is active", async () => {
  const queued = { ...completedRender, id: 32, version: 3, status: "queued" as const, progress: 0, output_file_name: null, output_file_size: null, output_duration_sec: null, output_width: null, output_height: null, preview_url: null, download_url: null, completed_at: null };
  vi.mocked(getDraftRenders).mockResolvedValue([]);
  vi.mocked(createRender).mockResolvedValue(queued);
  const before = vi.fn().mockResolvedValue(true);
  render(<RenderPanel draftId={17} saveState="dirty" hasRequiredData onBeforeRender={before} />);
  await userEvent.click(await screen.findByRole("button", { name: "쇼츠 생성" }));
  expect(before).toHaveBeenCalledOnce();
  expect(createRender).toHaveBeenCalledWith(17);
  expect(screen.getByRole("button", { name: "쇼츠 생성 중…" })).toBeDisabled();
  expect(screen.getByText("0%")).toBeInTheDocument();
});

it("shows the actual completed MP4, download, version history, and retryable failure", async () => {
  const failed = { ...completedRender, id: 30, version: 1, status: "failed" as const, progress: 30, error_code: "ffmpeg_failed", error_message: "쇼츠 영상 생성에 실패했습니다.", output_file_name: null, output_file_size: null, output_duration_sec: null, output_width: null, output_height: null, preview_url: null, download_url: null, completed_at: "2026-08-05T09:00:00Z" };
  vi.mocked(getDraftRenders).mockResolvedValue([completedRender, failed]);
  render(<RenderPanel draftId={17} saveState="saved" hasRequiredData onBeforeRender={vi.fn().mockResolvedValue(true)} />);
  expect(await screen.findByLabelText("완성 쇼츠 버전 2")).toHaveAttribute("src", expect.stringContaining("/api/renders/31/video"));
  expect(screen.getByRole("link", { name: "MP4 다운로드" })).toHaveAttribute("href", expect.stringContaining("/api/renders/31/download"));
  expect(screen.getByRole("button", { name: /v2 · 완료/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /v1 · 실패/ }));
  expect(screen.getByRole("alert")).toHaveTextContent("쇼츠 영상 생성에 실패했습니다.");
  expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
});

it("autosaves changed template settings and reports completion", async () => {
  vi.mocked(getDraft).mockResolvedValue(draftFixture);
  vi.mocked(getTranscript).mockResolvedValue(transcriptFixture);
  vi.mocked(updateDraft).mockResolvedValue(draftFixture);
  vi.mocked(saveDraftSubtitles).mockResolvedValue({ ...draftFixture, custom_title: "변경 제목", updated_at: "2026-08-04T08:01:00Z" });
  render(<ShortsEditorPage draftId={17} />);
  const titleInput = await screen.findByLabelText("쇼츠 큰 제목");
  fireEvent.change(titleInput, { target: { value: "변경 제목" } });
  fireEvent.change(screen.getByLabelText("영상 영역 위아래 위치"), { target: { value: "0.4" } });
  expect(screen.getByText("저장되지 않은 변경사항")).toBeInTheDocument();
  await waitFor(() => expect(updateDraft).toHaveBeenCalledWith(17, expect.objectContaining({ custom_title: "변경 제목", video_area_position_y: 0.4, playback_rate: 1, template_type: "sermon_letterbox_v1" })), { timeout: 1800 });
  await waitFor(() => expect(screen.getByText("저장됨")).toBeInTheDocument());
});

it("applies the video position reset to the loaded editor state", async () => {
  const movedDraft = {
    ...draftFixture,
    zoom_scale: 1.34,
    crop_position_x: 0.82,
    crop_position_y: 0.17,
    video_area_position_y: 0.42,
    video_area_height: 0.53,
  };
  vi.mocked(getDraft).mockResolvedValue(movedDraft);
  vi.mocked(getTranscript).mockResolvedValue(transcriptFixture);
  vi.mocked(updateDraft).mockResolvedValue({ ...movedDraft, ...LETTERBOX_COMPOSITION_RESET });
  vi.mocked(saveDraftSubtitles).mockResolvedValue({ ...movedDraft, ...LETTERBOX_COMPOSITION_RESET });
  render(<ShortsEditorPage draftId={17} />);
  await screen.findByLabelText("영상 확대");
  await userEvent.click(screen.getByRole("button", { name: "영상 위치 초기화" }));
  expect(screen.getByLabelText("영상 확대")).toHaveValue("1");
  expect(screen.getByLabelText("영상 가로 위치")).toHaveValue("0.5");
  expect(screen.getByLabelText("영상 세로 위치")).toHaveValue("0.5");
  expect(screen.getByLabelText("영상 영역 위아래 위치")).toHaveValue("0.3");
  await waitFor(
    () => expect(updateDraft).toHaveBeenCalledWith(17, expect.objectContaining(LETTERBOX_COMPOSITION_RESET)),
    { timeout: 1800 },
  );
});

it("keeps preview values and displays an autosave failure", async () => {
  vi.mocked(getDraft).mockResolvedValue(draftFixture);
  vi.mocked(getTranscript).mockResolvedValue(transcriptFixture);
  vi.mocked(updateDraft).mockRejectedValue(new Error("저장 서버 오류"));
  render(<ShortsEditorPage draftId={17} />);
  const titleInput = await screen.findByLabelText("쇼츠 큰 제목");
  fireEvent.change(titleInput, { target: { value: "저장되지 않은 제목" } });
  await waitFor(() => expect(screen.getByText("저장 실패")).toBeInTheDocument(), { timeout: 1800 });
  expect(screen.getByLabelText("쇼츠 큰 제목")).toHaveValue("저장되지 않은 제목");
  expect(screen.getByText("저장 서버 오류")).toBeInTheDocument();
});

it("autosaves a word highlight and keeps the local range when saving fails", async () => {
  const unselectedDraft = { ...draftFixture, title_highlight_ranges: [] };
  vi.mocked(getDraft).mockResolvedValue(unselectedDraft);
  vi.mocked(getTranscript).mockResolvedValue(transcriptFixture);
  vi.mocked(updateDraft).mockRejectedValue(new Error("강조 저장 오류"));
  render(<ShortsEditorPage draftId={17} />);
  const word = await screen.findByRole("button", { name: "큰, 강조 안 됨" });
  word.focus();
  await userEvent.keyboard("{Enter}");
  expect(screen.getByRole("button", { name: "큰, 전체 강조됨" })).toHaveAttribute("aria-pressed", "true");
  await waitFor(() => expect(updateDraft).toHaveBeenCalledWith(17, expect.objectContaining({ title_highlight_ranges: [{ start: 0, end: 1 }] })), { timeout: 1800 });
  await waitFor(() => expect(screen.getByText("저장 실패")).toBeInTheDocument(), { timeout: 1800 });
  expect(screen.getByRole("button", { name: "큰, 전체 강조됨" })).toBeInTheDocument();
  expect(screen.getByText("강조 저장 오류")).toBeInTheDocument();
});

describe("validation hints", () => {
  it("warns for long or multiline subtitle text", () => {
    render(<SubtitleEditor subtitles={[{ ...subtitles[0], edited_text: `${"가".repeat(40)}\n둘째 줄\n셋째 줄`, is_edited: true }]} activeSubtitleId={null} onChange={vi.fn()} onPlay={vi.fn()} onSplit={vi.fn()} onMerge={vi.fn()} onResetOne={vi.fn()} onResetAll={vi.fn()} />);
    expect(screen.getByText(/한 화면에 표시하기에는 자막이 길 수 있습니다/)).toBeInTheDocument();
    expect(screen.getByText(/세 줄 이상/)).toBeInTheDocument();
  });

  it("warns when the current letterbox subtitle has three lines", () => {
    const multiline = { ...subtitles[0], edited_text: "첫째 줄\n둘째 줄\n셋째 줄" };
    render(<TemplateSettingsPanel settings={visualSettings} currentSubtitle={multiline} showSafeAreas onShowSafeAreasChange={vi.fn()} onChange={vi.fn()} />);
    expect(screen.getByText(/자막이 세 줄 이상입니다/)).toBeInTheDocument();
  });
});
