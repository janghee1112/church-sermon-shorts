"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createRender, getDraftRenders, getRender, renderDownloadUrl, renderVideoUrl } from "@/lib/api";
import { formatTime } from "@/lib/time";
import type { RenderJob } from "@/types";


const STEP_LABELS: Record<string, string> = {
  validating: "편집 설정 확인",
  preparing_assets: "제목·자막 준비",
  cutting_source: "영상 준비",
  composing_video: "영상 구성",
  rendering_text: "제목·자막 합성",
  encoding: "쇼츠 영상 생성",
  finalizing: "최종 파일 확인",
};

function formatBytes(value: number | null): string {
  if (!value) return "-";
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.round(value / 1024)} KB`;
}

interface Props {
  draftId: number;
  saveState: "saved" | "dirty" | "saving" | "error";
  hasRequiredData: boolean;
  onBeforeRender: () => Promise<boolean>;
}

export function RenderPanel({ draftId, saveState, hasRequiredData, onBeforeRender }: Props) {
  const [renders, setRenders] = useState<RenderJob[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  const refreshList = useCallback(async () => {
    const loaded = await getDraftRenders(draftId);
    setRenders(loaded);
    setSelectedId((current) => current ?? loaded.find((item) => item.status === "completed")?.id ?? loaded[0]?.id ?? null);
  }, [draftId]);

  useEffect(() => {
    void refreshList().catch((caught) => setError(caught instanceof Error ? caught.message : "렌더링 목록을 불러오지 못했습니다."));
  }, [refreshList]);

  const activeRender = renders.find((item) => ["queued", "preparing", "rendering"].includes(item.status));
  useEffect(() => {
    if (!activeRender) return;
    const timer = window.setInterval(() => {
      void getRender(activeRender.id).then((next) => {
        setRenders((current) => [next, ...current.filter((item) => item.id !== next.id)].sort((a, b) => b.version - a.version));
        if (next.status === "completed") setSelectedId(next.id);
      }).catch((caught) => {
        window.clearInterval(timer);
        setError(caught instanceof Error ? caught.message : "렌더링 상태를 확인하지 못했습니다.");
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeRender?.id]);

  const selected = useMemo(
    () => renders.find((item) => item.id === selectedId) ?? renders.find((item) => item.status === "completed") ?? null,
    [renders, selectedId],
  );

  async function start() {
    setStarting(true);
    setError("");
    try {
      if (!(await onBeforeRender())) return;
      const job = await createRender(draftId);
      setRenders((current) => [job, ...current.filter((item) => item.id !== job.id)].sort((a, b) => b.version - a.version));
      setSelectedId(job.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "쇼츠 생성을 시작하지 못했습니다.");
    } finally {
      setStarting(false);
    }
  }

  const busy = starting || Boolean(activeRender);
  return (
    <section aria-label="쇼츠 생성" className="rounded-2xl bg-white p-5 shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-[11px] font-black tracking-[.16em] text-gold">4 · RENDER</p><h2 className="serif mt-1 text-xl font-bold">완성 쇼츠</h2><p className="mt-1 text-xs text-ink/45">저장된 편집값으로 실제 1080×1920 MP4를 만듭니다.</p></div>
        <button type="button" onClick={() => void start()} disabled={busy || saveState === "saving" || !hasRequiredData} className="focus-ring rounded-xl bg-moss px-5 py-3 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-45">{busy ? "쇼츠 생성 중…" : "쇼츠 생성"}</button>
      </div>
      {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-bold text-red-700">{error}</p>}
      {activeRender && <div className="mt-5" aria-live="polite"><div className="flex justify-between text-sm font-bold"><span>{STEP_LABELS[activeRender.current_step] ?? "쇼츠 생성"}</span><span>{activeRender.progress}%</span></div><div className="mt-2 h-2.5 overflow-hidden rounded-full bg-ink/10"><div className="h-full rounded-full bg-gold transition-[width]" style={{ width: `${activeRender.progress}%` }} /></div></div>}
      {selected?.status === "failed" && <div role="alert" className="mt-5 rounded-xl bg-red-50 p-4"><p className="font-bold text-red-800">버전 {selected.version} 생성 실패</p><p className="mt-1 text-sm text-red-700">{selected.error_message ?? "쇼츠 영상 생성에 실패했습니다."}</p><button type="button" onClick={() => void start()} disabled={busy} className="focus-ring mt-3 rounded-lg bg-red-700 px-3 py-2 text-xs font-bold text-white">다시 시도</button></div>}
      {selected?.status === "completed" && <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(220px,320px)_1fr]">
        <video key={selected.id} src={renderVideoUrl(selected.id)} controls playsInline preload="metadata" className="aspect-[9/16] w-full rounded-2xl bg-black object-contain" aria-label={`완성 쇼츠 버전 ${selected.version}`} />
        <div className="self-center"><h3 className="text-lg font-black">완성본 v{selected.version}</h3><dl className="mt-3 grid grid-cols-2 gap-2 text-sm"><div><dt className="text-ink/45">길이</dt><dd className="font-bold">{formatTime(selected.output_duration_sec ?? 0)}</dd></div><div><dt className="text-ink/45">해상도</dt><dd className="font-bold">{selected.output_width}×{selected.output_height}</dd></div><div><dt className="text-ink/45">파일 크기</dt><dd className="font-bold">{formatBytes(selected.output_file_size)}</dd></div><div><dt className="text-ink/45">완료 시각</dt><dd className="font-bold">{selected.completed_at ? new Date(selected.completed_at).toLocaleString("ko-KR") : "-"}</dd></div></dl><div className="mt-5 flex flex-wrap gap-2"><a href={renderDownloadUrl(selected.id)} className="focus-ring rounded-lg bg-gold px-4 py-2.5 text-sm font-black text-ink">MP4 다운로드</a><button type="button" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} className="focus-ring rounded-lg border border-ink/10 px-4 py-2.5 text-sm font-bold">편집으로 돌아가기</button><button type="button" onClick={() => void start()} disabled={busy} className="focus-ring rounded-lg bg-moss px-4 py-2.5 text-sm font-bold text-white disabled:opacity-45">다시 렌더링</button></div></div>
      </div>}
      {renders.length > 0 && <div className="mt-6"><h3 className="text-sm font-black">최근 버전</h3><div className="mt-2 flex flex-wrap gap-2">{renders.slice(0, 5).map((item) => <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`focus-ring rounded-lg border px-3 py-2 text-xs font-bold ${selected?.id === item.id ? "border-moss bg-mint text-moss" : "border-ink/10 bg-cream"}`}>v{item.version} · {item.status === "completed" ? "완료" : item.status === "failed" ? "실패" : `${item.progress}%`}</button>)}</div></div>}
    </section>
  );
}
