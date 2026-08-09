import type { CandidateResults, ClipDraft, DraftEditableSettings, DraftSubtitle, Project, RenderJob, TitleHighlightRange, TitleLayoutPreview, Transcript } from "@/types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail ?? "요청을 처리하지 못했습니다.");
  }
  return response.json() as Promise<T>;
}

interface UploadConfig {
  storage_backend: "local" | "r2";
  multipart_enabled: boolean;
  part_size: number | null;
}

interface MultipartInit {
  session_id: string;
  project_id: string;
  upload_id: string;
  object_key: string;
  part_size: number;
  total_parts: number;
  parts: Array<{ part_number: number; upload_url: string }>;
}

function uploadLocalProject(file: File, onProgress: (progress: number) => void): Promise<Project> {
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

function uploadPart(
  url: string,
  body: Blob,
  onProgress: (loaded: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.upload.addEventListener("progress", (event) => onProgress(event.loaded));
    request.addEventListener("load", () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new Error("영상 조각 업로드에 실패했습니다."));
        return;
      }
      const etag = request.getResponseHeader("ETag");
      if (!etag) {
        reject(new Error("R2 업로드 확인값을 받지 못했습니다. CORS의 ETag 노출 설정을 확인해 주세요."));
        return;
      }
      resolve(etag);
    });
    request.addEventListener("error", () => reject(new Error("R2에 연결할 수 없습니다.")));
    request.send(body);
  });
}

async function uploadR2Project(
  file: File,
  onProgress: (progress: number) => void,
  onVerifying?: (value: boolean) => void,
): Promise<Project> {
  const session = await fetch(`${API_BASE}/api/uploads/multipart/init`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_name: file.name, file_size: file.size, content_type: file.type }),
  }).then(parseResponse<MultipartInit>);
  const loadedByPart = new Map<number, number>();
  const completed: Array<{ part_number: number; etag: string }> = [];
  let nextIndex = 0;
  const updateProgress = (partNumber: number, loaded: number) => {
    loadedByPart.set(partNumber, loaded);
    const totalLoaded = Array.from(loadedByPart.values()).reduce((sum, value) => sum + value, 0);
    onProgress(Math.min(99, Math.round((totalLoaded / file.size) * 100)));
  };
  const worker = async () => {
    while (nextIndex < session.parts.length) {
      const part = session.parts[nextIndex++];
      const start = (part.part_number - 1) * session.part_size;
      const body = file.slice(start, Math.min(file.size, start + session.part_size));
      let lastError: unknown;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const etag = await uploadPart(part.upload_url, body, (loaded) => updateProgress(part.part_number, loaded));
          completed.push({ part_number: part.part_number, etag });
          lastError = null;
          break;
        } catch (reason) {
          lastError = reason;
          loadedByPart.set(part.part_number, 0);
        }
      }
      if (lastError) throw lastError;
    }
  };
  try {
    await Promise.all(Array.from({ length: Math.min(3, session.parts.length) }, () => worker()));
    onProgress(100);
    onVerifying?.(true);
    return await fetch(`${API_BASE}/api/uploads/multipart/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id, parts: completed }),
    }).then(parseResponse<Project>);
  } catch (reason) {
    await fetch(`${API_BASE}/api/uploads/multipart/abort`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id }),
    }).catch(() => undefined);
    throw reason;
  } finally {
    onVerifying?.(false);
  }
}

export async function uploadProject(
  file: File,
  onProgress: (progress: number) => void,
  onVerifying?: (value: boolean) => void,
): Promise<Project> {
  const config = await fetch(`${API_BASE}/api/uploads/config`, { cache: "no-store" }).then(parseResponse<UploadConfig>);
  return config.storage_backend === "r2" && config.multipart_enabled
    ? uploadR2Project(file, onProgress, onVerifying)
    : uploadLocalProject(file, onProgress);
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
