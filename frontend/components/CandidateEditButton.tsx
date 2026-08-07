"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createDraft } from "@/lib/api";

export function CandidateEditButton({ projectId, candidateId, selectedTitleOrder }: { projectId: string; candidateId: number; selectedTitleOrder: number | null }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function openEditor() {
    if (selectedTitleOrder === null) return;
    setLoading(true);
    setError("");
    try {
      const draft = await createDraft(projectId, candidateId, selectedTitleOrder);
      router.push(`/editor/${draft.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "편집 화면을 열지 못했습니다.");
      setLoading(false);
    }
  }

  return (
    <div onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        disabled={loading || selectedTitleOrder === null}
        onClick={openEditor}
        className="focus-ring w-full rounded-xl bg-moss px-4 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? "편집 초안 준비 중…" : "이 후보 편집하기"}
      </button>
      {error && <p role="alert" className="mt-2 text-xs font-bold text-red-700">{error}</p>}
    </div>
  );
}
