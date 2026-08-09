"use client";

import { useState } from "react";
import { deleteProject } from "@/lib/api";
import { clearProjectStorage } from "@/lib/projectStorage";

interface Props {
  projectId: string;
  onDeleted: () => void;
  className?: string;
}

export function NewProjectButton({ projectId, onDeleted, className = "" }: Props) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  async function confirmDelete() {
    if (deleting) return;
    setDeleting(true);
    setError("");
    try {
      await deleteProject(projectId);
      clearProjectStorage();
      onDeleted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "현재 작업을 정리하지 못했습니다. 다시 시도해 주세요.");
      setDeleting(false);
    }
  }

  return (
    <>
      <button type="button" onClick={() => { setError(""); setOpen(true); }} className={className}>
        새 영상 분석
      </button>
      {open && (
        <div role="dialog" aria-modal="true" aria-labelledby="new-project-title" className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-5">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            <h2 id="new-project-title" className="serif text-xl font-bold">새 영상 분석을 시작하시겠습니까?</h2>
            <p className="mt-3 text-sm font-bold leading-6 text-red-700">현재 작업 중인 영상과 편집 결과가 모두 삭제됩니다.</p>
            <p className="mt-4 text-sm font-bold text-ink/70">삭제되는 항목</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-ink/65">
              <li>업로드한 원본 영상</li>
              <li>분석된 대본과 추천 쇼츠 후보</li>
              <li>편집 내용</li>
              <li>생성한 V1, V2, V3 등의 쇼츠 영상</li>
            </ul>
            <p className="mt-4 text-sm leading-6 text-ink/65">완성된 영상이 필요하다면 먼저 MP4를 다운로드해 주세요. 삭제 후에는 현재 작업을 복구할 수 없습니다.</p>
            {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm font-bold text-red-700">{error}</p>}
            <div className="mt-6 flex flex-col-reverse justify-end gap-2 sm:flex-row">
              <button type="button" disabled={deleting} onClick={() => setOpen(false)} className="focus-ring rounded-lg border border-ink/10 px-4 py-2.5 text-sm font-bold disabled:opacity-45">취소</button>
              <button type="button" disabled={deleting} onClick={() => void confirmDelete()} className="focus-ring rounded-lg bg-red-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-45">
                {deleting ? "현재 작업을 정리하는 중…" : "현재 작업 삭제 후 새 영상 시작"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
