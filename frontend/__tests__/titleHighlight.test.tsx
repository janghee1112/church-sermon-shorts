import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { HighlightedTitle } from "@/components/editor/HighlightedTitle";
import { TitleHighlightEditor } from "@/components/editor/TitleHighlightEditor";
import { TemplateSettingsPanel } from "@/components/editor/TemplateSettingsPanel";
import {
  getTokenHighlightState,
  normalizeHighlightRanges,
  splitTitleIntoHighlightSegments,
  tokenizeTitle,
} from "@/lib/titleHighlightRanges";
import type { DraftVisualSettings, TitleHighlightRange } from "@/types";

function HighlightHarness({ title, initial = [] }: { title: string; initial?: TitleHighlightRange[] }) {
  const [ranges, setRanges] = useState(initial);
  return <>
    <TitleHighlightEditor title={title} ranges={ranges} onChange={setRanges} />
    <div data-testid="range-preview"><HighlightedTitle title={title} ranges={ranges} /></div>
    <output data-testid="ranges-json">{JSON.stringify(ranges)}</output>
  </>;
}

describe("title highlight range utilities", () => {
  it("tokenizes words without losing multiple-space, newline, or Unicode code-point offsets", () => {
    expect(tokenizeTitle("자족은   무엇인가?\n🙏 믿음")).toEqual([
      { id: "token-0-3", text: "자족은", start: 0, end: 3, lineIndex: 0 },
      { id: "token-6-11", text: "무엇인가?", start: 6, end: 11, lineIndex: 0 },
      { id: "token-12-13", text: "🙏", start: 12, end: 13, lineIndex: 1 },
      { id: "token-14-16", text: "믿음", start: 14, end: 16, lineIndex: 1 },
    ]);
  });

  it("sorts, deduplicates, merges touching ranges, and removes invalid or whitespace-only ranges", () => {
    expect(normalizeHighlightRanges("가나 다라", [
      { start: 3, end: 5 }, { start: 1, end: 3 }, { start: 0, end: 2 },
      { start: 2, end: 3 }, { start: -1, end: 1 }, { start: 0, end: 99 },
    ])).toEqual([{ start: 0, end: 5 }]);
    expect(normalizeHighlightRanges("가 나", [{ start: 1, end: 2 }])).toEqual([]);
  });

  it("splits repeated text by exact position and preserves whitespace and line breaks", () => {
    const title = "믿음은 믿음을\n낳는다";
    const segments = splitTitleIntoHighlightSegments(title, [{ start: 4, end: 6 }]);
    expect(segments.map((segment) => segment.text).join("")).toBe(title);
    expect(segments.filter((segment) => segment.highlight).map((segment) => segment.text)).toEqual(["믿음"]);
    expect(segments.find((segment) => segment.start === 0)?.highlight).toBe(false);
  });

  it("reports none, full, and partial token states", () => {
    const token = tokenizeTitle("자족은")[0];
    expect(getTokenHighlightState(token, [])).toBe("none");
    expect(getTokenHighlightState(token, [{ start: 0, end: 3 }])).toBe("full");
    expect(getTokenHighlightState(token, [{ start: 0, end: 2 }])).toBe("partial");
  });
});

describe("title highlight editor", () => {
  it("selects multiple separated words and a specific repeated occurrence", async () => {
    render(<HighlightHarness title="믿음은 믿음을 낳는다" />);
    const wordButtons = screen.getAllByRole("button", { name: /믿음.*강조 안 됨/ });
    await userEvent.click(wordButtons[1]);
    await userEvent.click(screen.getByRole("button", { name: "낳는다, 강조 안 됨" }));
    expect(screen.getByTestId("ranges-json")).toHaveTextContent('[{"start":4,"end":7},{"start":8,"end":11}]');
    const highlights = screen.getAllByTestId("title-highlight");
    expect(highlights.map((item) => item.textContent)).toEqual(["믿음을", "낳는다"]);
    expect(screen.getAllByRole("button", { name: /믿음/ })[0]).toHaveAttribute("aria-pressed", "false");
  });

  it("opens the detail dialog, selects a partial character range, applies it, and restores focus", async () => {
    render(<HighlightHarness title="자족은 무엇인가?" initial={[{ start: 0, end: 3 }]} />);
    const tokenButton = screen.getByRole("button", { name: "자족은, 전체 강조됨" });
    await userEvent.click(tokenButton);
    const dialog = screen.getByRole("dialog", { name: "어절 세부 강조" });
    expect(dialog).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "자, 강조 선택됨" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "족, 강조 선택 안 됨" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "적용" }));
    expect(screen.getByRole("button", { name: "자족은, 일부 글자 강조됨" })).toHaveAttribute("data-highlight-state", "partial");
    expect(screen.getByTestId("ranges-json")).toHaveTextContent('[{"start":0,"end":2}]');
    await waitFor(() => expect(screen.getByRole("button", { name: "자족은, 일부 글자 강조됨" })).toHaveFocus());
  });

  it("supports full selection, removal, cancellation, and Escape", async () => {
    render(<HighlightHarness title="자족은 무엇인가?" initial={[{ start: 0, end: 2 }]} />);
    const partial = screen.getByRole("button", { name: "자족은, 일부 글자 강조됨" });
    await userEvent.click(partial);
    await userEvent.click(screen.getByRole("button", { name: "전체 선택" }));
    await userEvent.click(screen.getByRole("button", { name: "적용" }));
    expect(screen.getByRole("button", { name: "자족은, 전체 강조됨" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "자족은, 전체 강조됨" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "자족은 강조 해제" }));
    expect(screen.getByRole("button", { name: "자족은, 강조 안 됨" })).toHaveAttribute("aria-pressed", "false");
  });
});

it("clears highlights with one notice only when the title actually changes", async () => {
  const initial: DraftVisualSettings = {
    custom_title: "자족은 무엇인가?", title_highlight_ranges: [{ start: 0, end: 2 }],
    zoom_scale: 1.12, crop_position_x: 0.5, crop_position_y: 0.5,
    video_area_position_y: 0.34, video_area_height: 0.48,
    title_font_scale: 1, title_position_y: 0.11, subtitle_font_scale: 1,
    subtitle_position_y: 0.25, playback_rate: 1, template_type: "sermon_letterbox_v1",
  };
  function PanelHarness() {
    const [settings, setSettings] = useState(initial);
    return <TemplateSettingsPanel settings={settings} currentSubtitle={null} showSafeAreas onShowSafeAreasChange={vi.fn()} onChange={(values) => setSettings((current) => ({ ...current, ...values }))} />;
  }
  render(<PanelHarness />);
  fireEvent.change(screen.getByLabelText("영상 확대"), { target: { value: "1.2" } });
  expect(screen.getByRole("button", { name: "자족은, 일부 글자 강조됨" })).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("쇼츠 큰 제목"), { target: { value: "바뀐 제목" } });
  expect(screen.getByRole("status")).toHaveTextContent("제목이 변경되어 기존 강조 선택이 초기화되었습니다.");
  expect(screen.getByRole("button", { name: "바뀐, 강조 안 됨" })).toBeInTheDocument();
});

it("does not show a reset notice when a title without highlights changes", () => {
  const settings: DraftVisualSettings = {
    custom_title: "기존 제목", title_highlight_ranges: [], zoom_scale: 1.12,
    crop_position_x: 0.5, crop_position_y: 0.5, video_area_position_y: 0.34,
    video_area_height: 0.48, title_font_scale: 1, title_position_y: 0.11,
    subtitle_font_scale: 1, subtitle_position_y: 0.25, playback_rate: 1, template_type: "sermon_letterbox_v1",
  };
  function PanelHarness() {
    const [value, setValue] = useState(settings);
    return <TemplateSettingsPanel settings={value} currentSubtitle={null} showSafeAreas onShowSafeAreasChange={vi.fn()} onChange={(next) => setValue((current) => ({ ...current, ...next }))} />;
  }
  render(<PanelHarness />);
  fireEvent.change(screen.getByLabelText("쇼츠 큰 제목"), { target: { value: "새 제목" } });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
