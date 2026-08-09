import { afterEach, expect, it, vi } from "vitest";
import { uploadProject } from "@/lib/api";


class SuccessfulPartRequest {
  status = 200;
  responseText = "";
  private listeners = new Map<string, Array<() => void>>();
  upload = {
    addEventListener: (name: string, callback: (event: { loaded: number }) => void) => {
      if (name === "progress") this.progress = callback;
    },
  };
  private progress?: (event: { loaded: number }) => void;

  open() {}

  addEventListener(name: string, callback: () => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), callback]);
  }

  getResponseHeader(name: string) {
    return name.toLowerCase() === "etag" ? '"part-etag"' : null;
  }

  send(body: Blob) {
    this.progress?.({ loaded: body.size });
    for (const callback of this.listeners.get("load") ?? []) callback();
  }
}


afterEach(() => {
  vi.unstubAllGlobals();
});


it("uploads multipart bytes directly to R2 and verifies before returning the project", async () => {
  const project = {
    project_id: "project-1", original_file_name: "sermon.mp4", stored_file_name: "source.mp4",
    duration_seconds: 120, width: 1920, height: 1080, file_size: 10,
    status: "uploaded", progress: 10, error_message: null, error_stage: null,
    analysis_mode: "real", created_at: "2026-01-01", updated_at: "2026-01-01",
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/uploads/config")) {
      return new Response(JSON.stringify({ storage_backend: "r2", multipart_enabled: true, part_size: 5 }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }
    if (url.endsWith("/api/uploads/multipart/init")) {
      return new Response(JSON.stringify({
        session_id: "session-1", project_id: "project-1", upload_id: "upload-1",
        object_key: "projects/project-1/original/source.mp4", part_size: 5, total_parts: 2,
        parts: [
          { part_number: 1, upload_url: "https://r2.example/part-1" },
          { part_number: 2, upload_url: "https://r2.example/part-2" },
        ],
      }), { status: 201, headers: { "Content-Type": "application/json" } });
    }
    if (url.endsWith("/api/uploads/multipart/complete")) {
      const payload = JSON.parse(String(init?.body));
      expect(payload.session_id).toBe("session-1");
      expect(payload.parts).toHaveLength(2);
      return new Response(JSON.stringify(project), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("XMLHttpRequest", SuccessfulPartRequest);
  const progress: number[] = [];
  const verifying: boolean[] = [];
  const result = await uploadProject(
    new File(["0123456789"], "sermon.mp4", { type: "video/mp4" }),
    (value) => progress.push(value),
    (value) => verifying.push(value),
  );
  expect(result.project_id).toBe("project-1");
  expect(progress.at(-1)).toBe(100);
  expect(verifying).toEqual([true, false]);
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/projects"))).toBe(false);
});
