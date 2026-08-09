import type { CandidateResults, ClipDraft, DraftEditableSettings, DraftSubtitle, Project, RenderJob, TitleHighlightRange, TitleLayoutPreview, Transcript } from "@/types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail ?? "요청을 처리하지 못했습니다.");
  }
  return response.json() as Promise<T>;
}

export function uploadProject(file: File, onProgress: (progress: number) => void): Promise<Project> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);
    request.open("POST", `${API_BASE}/api/projects`);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    request.addEventListener("load", () => {
      const payload = JSON.parse(request.responseText || "{}") as Project & { detail?: string };
      if (request.status >= 200 && request.status < 300) resolve(payload);
      else reject(new Error(payload.detail ?? "영상 업로드에 실패했습니다."));
    });
    request.addEventListener("error", () => reject(new Error("서버에 연결할 수 없습니다.")));
    request.send(formData);
  });
}

export const startAnalysis = (projectId: string) =>
  fetch(`${API_BASE}/api/projects/${projectId}/analyze`, { method: "POST" }).then(parseResponse<Project>);

export const getProject = (projectId: string) =>
  fetch(`${API_BASE}/api/projects/${projectId}`, { cache: "no-store" }).then(parseResponse<Project>);

export const getTranscript = (projectId: string) =>
  fetch(`${API_BASE}/api/projects/${projectId}/transcript`).then(parseResponse<Transcript>);

export const getCandidates = (projectId: string) =>
  fetch(`${API_BASE}/api/projects/${projectId}/candidates`).then(parseResponse<CandidateResults>);

export async function deleteProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}`, { method: "DELETE" });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail ?? "현재 작업을 정리하지 못했습니다. 다시 시도해 주세요.");
  }
}

export const videoUrl = (projectId: string) => `${API_BASE}/api/projects/${projectId}/video`;

export const getTitleLayoutPreview = (
  title: string,
  titleFontScale: number,
  titlePositionY: number,
  titleHighlightRanges: TitleHighlightRange[],
  signal?: AbortSignal,
) => fetch(`${API_BASE}/api/title-layout/preview`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    title,
    title_font_scale: titleFontScale,
    title_position_y: titlePositionY,
    title_highlight_ranges: titleHighlightRanges,
  }),
  signal,
}).then(parseResponse<TitleLayoutPreview>);

export const createDraft = (projectId: string, candidateId: number, selectedTitleOrder: number) =>
  fetch(`${API_BASE}/api/projects/${projectId}/drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_id: candidateId, selected_title_order: selectedTitleOrder }),
  }).then(parseResponse<ClipDraft>);

export const getDraft = (draftId: number) =>
  fetch(`${API_BASE}/api/drafts/${draftId}`, { cache: "no-store" }).then(parseResponse<ClipDraft>);

export const updateDraft = (
  draftId: number,
  values: Partial<DraftEditableSettings & Pick<ClipDraft, "status">>,
) => fetch(`${API_BASE}/api/drafts/${draftId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(values),
}).then(parseResponse<ClipDraft>);

export const updateDraftRange = (
  draftId: number,
  startSegmentId: number,
  endSegmentId: number,
) => fetch(`${API_BASE}/api/drafts/${draftId}/range`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    start_segment_id: startSegmentId,
    end_segment_id: endSegmentId,
    regenerate_subtitles: true,
  }),
}).then(parseResponse<ClipDraft>);

export const saveDraftSubtitles = (draftId: number, subtitles: DraftSubtitle[]) =>
  fetch(`${API_BASE}/api/drafts/${draftId}/subtitles`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subtitles: subtitles.map(({ id, cue_order, start_sec, end_sec, edited_text }) => ({
        id, cue_order, start_sec, end_sec, edited_text,
      })),
    }),
  }).then(parseResponse<ClipDraft>);

export const splitDraftSubtitle = (draftId: number, subtitleId: number, splitIndex: number) =>
  fetch(`${API_BASE}/api/drafts/${draftId}/subtitles/${subtitleId}/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ split_index: splitIndex }),
  }).then(parseResponse<ClipDraft>);

export const mergeDraftSubtitles = (draftId: number, firstSubtitleId: number, secondSubtitleId: number) =>
  fetch(`${API_BASE}/api/drafts/${draftId}/subtitles/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ first_subtitle_id: firstSubtitleId, second_subtitle_id: secondSubtitleId }),
  }).then(parseResponse<ClipDraft>);

export const resetDraftSubtitles = (draftId: number) =>
  fetch(`${API_BASE}/api/drafts/${draftId}/subtitles/reset`, { method: "POST" }).then(parseResponse<ClipDraft>);

export const createRender = (draftId: number) =>
  fetch(`${API_BASE}/api/drafts/${draftId}/renders`, { method: "POST" }).then(parseResponse<RenderJob>);

export const getRender = (renderId: number) =>
  fetch(`${API_BASE}/api/renders/${renderId}`, { cache: "no-store" }).then(parseResponse<RenderJob>);

export const getDraftRenders = (draftId: number) =>
  fetch(`${API_BASE}/api/drafts/${draftId}/renders`, { cache: "no-store" }).then(parseResponse<RenderJob[]>);

export const renderVideoUrl = (renderId: number) => `${API_BASE}/api/renders/${renderId}/video`;
export const renderDownloadUrl = (renderId: number) => `${API_BASE}/api/renders/${renderId}/download`;
