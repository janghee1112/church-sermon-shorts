"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getDraft,
  getTranscript,
  mergeDraftSubtitles,
  resetDraftSubtitles,
  saveDraftSubtitles,
  splitDraftSubtitle,
  updateDraft,
  updateDraftRange,
} from "@/lib/api";
import type { ClipDraft, DraftSubtitle, Transcript } from "@/types";
import { ConfirmDialog } from "./ConfirmDialog";
import { SubtitleEditor } from "./SubtitleEditor";
import { TranscriptRangeSelector } from "./TranscriptRangeSelector";
import { VerticalVideoPreview, type VideoPreviewHandle } from "./VerticalVideoPreview";
import { TemplateSettingsPanel } from "./TemplateSettingsPanel";
import { RenderPanel } from "./RenderPanel";
import { NewProjectButton } from "@/components/NewProjectButton";

type SaveState = "saved" | "dirty" | "saving" | "error";
type ConfirmAction = "range" | "reset" | null;

export function ShortsEditorPage({ draftId }: { draftId: number }) {
  const router = useRouter();
  const previewRef = useRef<VideoPreviewHandle>(null);
  const revisionRef = useRef(0);
  const savingRef = useRef(false);
  const latestDraftRef = useRef<ClipDraft | null>(null);
  const [draft, setDraft] = useState<ClipDraft | null>(null);
  const [savedDraft, setSavedDraft] = useState<ClipDraft | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [pendingStartId, setPendingStartId] = useState(0);
  const [pendingEndId, setPendingEndId] = useState(0);
  const [activeSubtitleId, setActiveSubtitleId] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [error, setError] = useState("");
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [showSafeAreas, setShowSafeAreas] = useState(true);

  useEffect(() => {
    if (!Number.isInteger(draftId) || draftId <= 0) { setError("올바르지 않은 편집 초안 주소입니다."); return; }
    Promise.all([getDraft(draftId), getDraft(draftId).then((item) => getTranscript(item.project_id))])
      .then(([loadedDraft, loadedTranscript]) => {
        latestDraftRef.current = loadedDraft;
        setDraft(loadedDraft);
        setSavedDraft(loadedDraft);
        setTranscript(loadedTranscript);
        setPendingStartId(loadedDraft.range.start_segment_id);
        setPendingEndId(loadedDraft.range.end_segment_id);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "편집 초안을 불러오지 못했습니다."));
  }, [draftId]);

  const saveAll = useCallback(async (): Promise<boolean> => {
    if (!latestDraftRef.current || savingRef.current) return false;
    savingRef.current = true;
    setError("");
    try {
      while (latestDraftRef.current) {
        const savingRevision = revisionRef.current;
        const snapshot = latestDraftRef.current;
        setSaveState("saving");
        await updateDraft(snapshot.id, {
          custom_title: snapshot.custom_title,
          title_highlight_ranges: snapshot.title_highlight_ranges,
          zoom_scale: snapshot.zoom_scale,
          crop_position_x: snapshot.crop_position_x,
          crop_position_y: snapshot.crop_position_y,
          video_area_position_y: snapshot.video_area_position_y,
          video_area_height: snapshot.video_area_height,
          title_font_scale: snapshot.title_font_scale,
          subtitle_font_scale: snapshot.subtitle_font_scale,
          subtitle_position_y: snapshot.subtitle_position_y,
          playback_rate: snapshot.playback_rate,
          template_type: snapshot.template_type,
          status: snapshot.status,
        });
        const saved = await saveDraftSubtitles(snapshot.id, snapshot.subtitles);
        setSavedDraft(saved);
        if (revisionRef.current !== savingRevision) continue;
        latestDraftRef.current = saved;
        setDraft(saved);
        setSaveState("saved");
        break;
      }
      return true;
    } catch (caught) {
      setSaveState("error");
      setError(caught instanceof Error ? caught.message : "변경 내용을 저장하지 못했습니다.");
      return false;
    } finally {
      savingRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (saveState !== "dirty") return;
    const timer = window.setTimeout(() => void saveAll(), 750);
    return () => window.clearTimeout(timer);
  }, [saveState, draft, saveAll]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (saveState === "dirty" || saveState === "saving") { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [saveState]);

  function updateLocal(values: Partial<ClipDraft>) {
    revisionRef.current += 1;
    setDraft((current) => {
      if (!current) return current;
      const next = { ...current, ...values };
      latestDraftRef.current = next;
      return next;
    });
    setSaveState("dirty");
  }

  function updateSubtitle(id: number, text: string) {
    if (!draft) return;
    updateLocal({ subtitles: draft.subtitles.map((item) => item.id === id ? { ...item, edited_text: text, is_edited: text !== item.original_text } : item) });
  }

  function acceptServerDraft(next: ClipDraft) {
    latestDraftRef.current = next;
    setDraft(next);
    setSavedDraft(next);
    revisionRef.current += 1;
    setPendingStartId(next.range.start_segment_id);
    setPendingEndId(next.range.end_segment_id);
    setSaveState("saved");
    setError("");
  }

  async function applyRange() {
    if (!draft) return;
    if (draft.subtitles.some((item) => item.is_edited)) { setConfirmAction("range"); return; }
    await performRangeChange();
  }

  async function performRangeChange() {
    if (!draft) return;
    setConfirmAction(null);
    setSaveState("saving");
    try { acceptServerDraft(await updateDraftRange(draft.id, pendingStartId, pendingEndId)); }
    catch (caught) { setSaveState("error"); setError(caught instanceof Error ? caught.message : "구간을 변경하지 못했습니다."); }
  }

  async function runSubtitleAction(action: () => Promise<ClipDraft>) {
    setSaveState("saving");
    try { acceptServerDraft(await action()); }
    catch (caught) { setSaveState("error"); setError(caught instanceof Error ? caught.message : "자막 작업을 처리하지 못했습니다."); }
  }

  function updateActiveSubtitle(seconds: number) {
    setCurrentTime(seconds);
    const active = draft?.subtitles.find((item) => seconds >= item.start_sec - 0.05 && seconds < item.end_sec + 0.05);
    setActiveSubtitleId(active?.id ?? null);
  }

  if (error && !draft) return <main className="grid min-h-screen place-items-center p-6"><div className="max-w-md rounded-2xl bg-white p-8 text-center shadow-soft"><h1 className="serif text-2xl font-bold">편집 화면을 열 수 없습니다</h1><p role="alert" className="mt-3 text-sm text-red-700">{error}</p><Link href="/" className="mt-6 inline-block rounded-lg bg-moss px-4 py-2 text-sm font-bold text-white">결과 화면으로</Link></div></main>;
  if (!draft || !transcript) return <main className="grid min-h-screen place-items-center"><p className="font-bold text-moss">편집 초안을 불러오는 중…</p></main>;

  const previewTitle = draft.custom_title;
  const activeSegmentId = transcript.segments.find((item) => currentTime >= item.start_sec - 0.05 && currentTime < item.end_sec + 0.05)?.id ?? null;
  const activeSubtitle = draft.subtitles.find((item) => item.id === activeSubtitleId) ?? null;
  return (
    <main className="min-h-screen pb-16">
      <header className="sticky top-0 z-30 border-b border-ink/10 bg-cream/90 px-4 py-3 backdrop-blur-xl sm:px-7">
        <div className="mx-auto flex max-w-[1600px] items-center gap-3"><Link href="/" className="focus-ring rounded-lg border border-ink/10 bg-white px-3 py-2 text-sm font-bold">← 결과</Link><div className="min-w-0 flex-1"><h1 className="truncate font-bold">후보 {draft.candidate.candidate_order} 편집 · {draft.candidate.main_topic}</h1><p className="truncate text-xs text-ink/45">{draft.project_original_file_name}</p></div><span aria-live="polite" data-saved-at={savedDraft?.updated_at ?? ""} className={`text-xs font-bold ${saveState === "error" ? "text-red-700" : "text-ink/50"}`}>{saveState === "saved" ? "저장됨" : saveState === "saving" ? "저장 중…" : saveState === "dirty" ? "저장되지 않은 변경사항" : "저장 실패"}</span><NewProjectButton projectId={draft.project_id} onDeleted={() => router.replace("/")} className="focus-ring rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-bold text-red-700" /><button type="button" onClick={() => void saveAll()} className="focus-ring rounded-lg bg-moss px-4 py-2 text-sm font-bold text-white">저장</button></div>
      </header>
      {draft.analysis_mode === "mock" && <div role="alert" className="mx-auto mt-5 max-w-[1600px] px-4 sm:px-7"><div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-bold text-amber-900">현재 Mock 모드입니다. 편집할 대본과 추천 구간은 실제 영상을 분석한 결과가 아닙니다.</div></div>}
      {error && <div role="alert" className="mx-auto mt-4 max-w-[1600px] px-4 text-sm font-bold text-red-700 sm:px-7">{error}</div>}
      <div className="mx-auto grid max-w-[1600px] gap-6 px-4 pt-6 sm:px-7 xl:grid-cols-[minmax(320px,.72fr)_minmax(0,1.28fr)]">
        <div className="xl:sticky xl:top-24 xl:self-start"><VerticalVideoPreview ref={previewRef} projectId={draft.project_id} startSec={draft.range.start_sec} endSec={draft.range.end_sec} title={previewTitle} settings={draft} subtitles={draft.subtitles} showSafeAreas={showSafeAreas} onTimeChange={updateActiveSubtitle} /></div>
        <div className="space-y-5">
          <TemplateSettingsPanel settings={draft} currentSubtitle={activeSubtitle} showSafeAreas={showSafeAreas} onShowSafeAreasChange={setShowSafeAreas} onChange={updateLocal} />
          <TranscriptRangeSelector segments={transcript.segments} pendingStartId={pendingStartId} pendingEndId={pendingEndId} recommendedStartId={draft.candidate.recommended_start_segment_id} recommendedEndId={draft.candidate.recommended_end_segment_id} activeSegmentId={activeSegmentId} onChange={(start, end) => { setPendingStartId(start); setPendingEndId(end); }} onApply={() => void applyRange()} onPlay={(start, end) => previewRef.current?.seekAndPlay(start, end)} />
          <div id="subtitle-editor"><SubtitleEditor subtitles={draft.subtitles} activeSubtitleId={activeSubtitleId} onChange={updateSubtitle} onPlay={(subtitle) => previewRef.current?.seekAndPlay(subtitle.start_sec, subtitle.end_sec)} onSplit={(id, splitIndex) => runSubtitleAction(() => splitDraftSubtitle(draft.id, id, splitIndex))} onMerge={(first, second) => runSubtitleAction(() => mergeDraftSubtitles(draft.id, first, second))} onResetOne={(id) => { const item = draft.subtitles.find((value) => value.id === id); if (item) updateSubtitle(id, item.original_text); }} onResetAll={() => setConfirmAction("reset")} /></div>
          <RenderPanel draftId={draft.id} saveState={saveState} hasRequiredData={draft.range.duration_sec > 0 && draft.subtitles.length > 0} onBeforeRender={() => saveState === "saved" ? Promise.resolve(true) : saveAll()} />
          <div className="flex justify-end"><button type="button" onClick={() => { updateLocal({ status: "ready" }); }} className="focus-ring rounded-xl bg-gold px-5 py-3 text-sm font-black text-ink">편집 완료 상태로 표시</button></div>
        </div>
      </div>
      {confirmAction === "range" && <ConfirmDialog title="구간을 변경할까요?" message="구간을 변경하면 현재 수정한 자막이 실제 대본을 기준으로 다시 생성됩니다." confirmLabel="구간 변경 및 자막 다시 만들기" onCancel={() => setConfirmAction(null)} onConfirm={() => void performRangeChange()} />}
      {confirmAction === "reset" && <ConfirmDialog title="자막을 모두 원문으로 복원할까요?" message="편집한 문구와 분할·병합 결과가 사라지고 현재 선택 구간의 전사 원문으로 다시 생성됩니다." confirmLabel="전체 복원" onCancel={() => setConfirmAction(null)} onConfirm={() => { setConfirmAction(null); void runSubtitleAction(() => resetDraftSubtitles(draft.id)); }} />}
    </main>
  );
}
