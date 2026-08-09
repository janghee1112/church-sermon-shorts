import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UploadPanel } from "@/components/UploadPanel";
import { ProgressPanel } from "@/components/ProgressPanel";
import { VideoWorkspace } from "@/components/VideoWorkspace";
import type { CandidateResults, Project, Transcript } from "@/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }));

const project: Project = {
  project_id: "p1", original_file_name: "sermon.mp4", stored_file_name: "p1.mp4", duration_seconds: 240,
  width: 1920, height: 1080, file_size: 1000, status: "completed", progress: 100,
  error_message: null, error_stage: null, analysis_mode: "real", created_at: "2026-01-01", updated_at: "2026-01-01",
};
const transcript: Transcript = { project_id: "p1", full_text: "믿음의 말씀", segments: [{ id: 1, start_sec: 10, end_sec: 20, text: "믿음의 말씀", segment_order: 0, words: [] }] };
const results: CandidateResults = { project_id: "p1", analysis_mode: "real", sermon_summary: "설교 요약", sermon_topics: ["믿음"], debug: null, candidates: [{
  id: 1, candidate_order: 1, recommendation_type: "핵심 메시지", start_sec: 30, end_sec: 90, duration_sec: 60,
  transcript: "실제 후보 대본", main_topic: "기다림의 믿음", selection_reason: "완결된 메시지",
  scores: { centrality: 90, standalone: 89, hook: 88, emotional_impact: 87, overall: 89 },
  titles: [1, 2, 3].map((number) => ({ title: `제목 ${number}`, title_type: "질문형", title_order: number })),
}] };

describe("upload", () => {
  it("selects a file and submits it", async () => {
    const onSubmit = vi.fn();
    render(<UploadPanel busy={false} progress={0} error={null} onSubmit={onSubmit} />);
    const file = new File(["video"], "sermon.mp4", { type: "video/mp4" });
    await userEvent.upload(screen.getByTestId("file-input"), file);
    expect(screen.getByText("sermon.mp4")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "업로드하고 분석 시작" }));
    expect(onSubmit).toHaveBeenCalledWith(file);
  });

  it("renders upload progress and error", () => {
    render(<UploadPanel busy progress={42} error="업로드 오류" onSubmit={vi.fn()} />);
    expect(screen.getByText("업로드 중 42%")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("업로드 오류");
  });
});

it("renders failed analysis with retry", async () => {
  const onRetry = vi.fn();
  render(<ProgressPanel project={{ ...project, status: "failed", progress: 40, error_stage: "transcribing", error_message: "전사 실패" }} onRetry={onRetry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("전사 실패");
  await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
  expect(onRetry).toHaveBeenCalled();
});

it("renders candidates, seeks, and pauses at preview end", async () => {
  render(<VideoWorkspace project={project} transcript={transcript} results={results} onNewProject={vi.fn()} />);
  const video = screen.getByTestId("video-player") as HTMLVideoElement;
  await userEvent.click(screen.getByRole("button", { name: "원문 검수 ▶" }));
  expect(video.currentTime).toBe(30);
  Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 15 });
  fireEvent.timeUpdate(video);
  expect(screen.getByTestId("transcript-segment-1")).toHaveClass("bg-mint");
  Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value: 89.95 });
  fireEvent.timeUpdate(video);
  expect(video.pause).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "00:10 세그먼트 재생" }));
  expect(video.currentTime).toBe(10);
});

it("lets the user select one of the three recommended titles", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 17 }), {
    status: 201,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<VideoWorkspace project={project} transcript={transcript} results={results} onNewProject={vi.fn()} />);
  const titleOptions = screen.getAllByRole("radio");
  expect(titleOptions).toHaveLength(3);
  expect(titleOptions[0]).not.toBeChecked();
  expect(screen.getByRole("button", { name: "이 후보 편집하기" })).toBeDisabled();
  await userEvent.click(titleOptions[1]);
  expect(titleOptions[1]).toBeChecked();
  expect(screen.getByRole("button", { name: "이 후보 편집하기" })).toBeEnabled();
  await userEvent.click(screen.getByRole("button", { name: "이 후보 편집하기" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const request = fetchMock.mock.calls[0][1] as RequestInit;
  expect(JSON.parse(String(request.body))).toEqual({ candidate_id: 1, selected_title_order: 2 });
  vi.unstubAllGlobals();
});

it("shows an explicit mock warning without presenting it as real analysis", () => {
  render(
    <VideoWorkspace
      project={{ ...project, analysis_mode: "mock" }}
      transcript={transcript}
      results={{ ...results, analysis_mode: "mock" }}
      onNewProject={vi.fn()}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "현재 Mock 모드입니다. 표시되는 대본과 추천 구간은 실제 영상을 분석한 결과가 아닙니다.",
  );
  expect(screen.getByText("Mock 샘플 대본")).toBeInTheDocument();
  expect(screen.queryByText("실제 전사 원문")).not.toBeInTheDocument();
  expect(screen.queryByText("실제 분석 결과")).not.toBeInTheDocument();
});

it("does not show the mock warning in real mode", () => {
  render(<VideoWorkspace project={project} transcript={transcript} results={results} onNewProject={vi.fn()} />);
  expect(screen.queryByText(/현재 Mock 모드입니다/)).not.toBeInTheDocument();
});

it("deletes the current project only after explicit new-video confirmation", async () => {
  const onNewProject = vi.fn();
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.setItem("sermon-shorts-project-id", project.project_id);
  render(<VideoWorkspace project={project} transcript={transcript} results={results} onNewProject={onNewProject} />);

  await userEvent.click(screen.getByRole("button", { name: "새 영상 분석" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("현재 작업 중인 영상과 편집 결과가 모두 삭제됩니다.");
  expect(fetchMock).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "취소" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(onNewProject).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "새 영상 분석" }));
  await userEvent.click(screen.getByRole("button", { name: "현재 작업 삭제 후 새 영상 시작" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/projects/p1", { method: "DELETE" }));
  expect(window.localStorage.getItem("sermon-shorts-project-id")).toBeNull();
  expect(onNewProject).toHaveBeenCalledOnce();
  vi.unstubAllGlobals();
});

it("keeps the current project when cleanup fails", async () => {
  const onNewProject = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "현재 쇼츠 영상 생성이 진행 중입니다." }), {
    status: 409,
    headers: { "Content-Type": "application/json" },
  })));
  window.localStorage.setItem("sermon-shorts-project-id", project.project_id);
  render(<VideoWorkspace project={project} transcript={transcript} results={results} onNewProject={onNewProject} />);

  await userEvent.click(screen.getByRole("button", { name: "새 영상 분석" }));
  await userEvent.click(screen.getByRole("button", { name: "현재 작업 삭제 후 새 영상 시작" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("현재 쇼츠 영상 생성이 진행 중입니다.");
  expect(window.localStorage.getItem("sermon-shorts-project-id")).toBe(project.project_id);
  expect(onNewProject).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});
