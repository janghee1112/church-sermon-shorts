"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { formatTime } from "@/lib/time";
import { videoUrl } from "@/lib/api";
import type { Candidate, CandidateResults, Project, Transcript } from "@/types";
import { CandidateEditButton } from "@/components/CandidateEditButton";
import { NewProjectButton } from "@/components/NewProjectButton";

interface Props {
  project: Project;
  transcript: Transcript;
  results: CandidateResults;
  onNewProject: () => void;
}

export function VideoWorkspace({ project, transcript, results, onNewProject }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const previewEndRef = useRef<number | null>(null);
  const previewStartRef = useRef<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [activeCandidateId, setActiveCandidateId] = useState<number | null>(null);
  const [search, setSearch] = useState("");

  const filteredSegments = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("ko");
    return query ? transcript.segments.filter((segment) => segment.text.toLocaleLowerCase("ko").includes(query)) : transcript.segments;
  }, [search, transcript.segments]);
  const activeSegmentId = useMemo(() => {
    const active = transcript.segments.find(
      (segment) => currentTime >= segment.start_sec - 0.05 && currentTime < segment.end_sec + 0.05,
    );
    return active?.id ?? null;
  }, [currentTime, transcript.segments]);

  useEffect(() => () => {
    previewEndRef.current = null;
    previewStartRef.current = null;
  }, []);

  function seekTo(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    previewEndRef.current = null;
    previewStartRef.current = null;
    setActiveCandidateId(null);
    video.currentTime = seconds;
    void video.play().catch(() => undefined);
  }

  function preview(candidate: Candidate) {
    const video = videoRef.current;
    if (!video) return;
    previewStartRef.current = candidate.start_sec;
    previewEndRef.current = candidate.end_sec;
    setActiveCandidateId(candidate.id);
    video.currentTime = candidate.start_sec;
    void video.play().catch(() => undefined);
  }

  function handleTimeUpdate() {
    const video = videoRef.current;
    if (!video) return;
    setCurrentTime(video.currentTime);
    const end = previewEndRef.current;
    if (end !== null && video.currentTime >= end - 0.12) {
      video.pause();
      previewEndRef.current = null;
      previewStartRef.current = null;
    }
  }

  function handleSeeking() {
    const video = videoRef.current;
    const start = previewStartRef.current;
    const end = previewEndRef.current;
    if (!video || start === null || end === null) return;
    if (video.currentTime < start - 0.5 || video.currentTime > end + 0.5) {
      previewEndRef.current = null;
      previewStartRef.current = null;
      setActiveCandidateId(null);
    }
  }

  return (
    <main className="min-h-screen pb-16">
      <header className="sticky top-0 z-20 border-b border-ink/10 bg-cream/85 px-5 py-4 backdrop-blur-xl sm:px-8">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-moss text-white">✦</span><div className="min-w-0"><p className="serif text-lg font-bold">말씀컷</p><p className="truncate text-xs text-ink/45">{project.original_file_name}</p></div></div>
          <NewProjectButton projectId={project.project_id} onDeleted={onNewProject} className="focus-ring shrink-0 rounded-xl border border-ink/15 bg-white px-4 py-2 text-sm font-bold" />
        </div>
      </header>

      {results.analysis_mode === "mock" && (
        <div role="alert" className="mx-auto mt-6 max-w-[1500px] px-5 sm:px-8">
          <div className="rounded-2xl border border-amber-300 bg-amber-50 px-5 py-4 text-sm font-bold leading-6 text-amber-900">
            현재 Mock 모드입니다. 표시되는 대본과 추천 구간은 실제 영상을 분석한 결과가 아닙니다.
          </div>
        </div>
      )}

      <div className="mx-auto grid max-w-[1500px] gap-7 px-5 pt-7 sm:px-8 xl:grid-cols-[minmax(0,1.08fr)_minmax(430px,.92fr)]">
        <section className="min-w-0 xl:sticky xl:top-24 xl:self-start">
          <div className="overflow-hidden rounded-[1.5rem] bg-black shadow-soft">
            <video
              ref={videoRef}
              data-testid="video-player"
              src={videoUrl(project.project_id)}
              controls
              preload="metadata"
              className="aspect-video w-full"
              onTimeUpdate={handleTimeUpdate}
              onSeeking={handleSeeking}
            />
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-ink/50"><span>현재 {formatTime(currentTime)} / {formatTime(project.duration_seconds)}</span>{activeCandidateId && <span className="rounded-full bg-mint px-3 py-1 font-bold text-moss">후보 구간 재생 중</span>}</div>

          <div className="mt-7 rounded-[1.5rem] border border-white bg-white/75 p-5 shadow-soft sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="serif text-2xl font-bold">전체 대본</h2><p className="mt-1 text-xs text-ink/45">시간을 누르면 영상이 바로 재생됩니다.</p></div><input aria-label="대본 검색" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="대본 검색" className="focus-ring rounded-xl border border-ink/10 bg-cream px-4 py-2.5 text-sm" /></div>
            <div className="scrollbar-thin mt-5 max-h-[440px] space-y-2 overflow-y-auto pr-2">
              {filteredSegments.map((segment) => (
                <div
                  key={segment.id}
                  data-testid={`transcript-segment-${segment.id}`}
                  className={`rounded-xl p-3 transition ${activeSegmentId === segment.id ? "bg-mint ring-2 ring-moss/30" : "hover:bg-mint/55"}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs font-bold text-moss">[{formatTime(segment.start_sec)} - {formatTime(segment.end_sec)}]</span>
                    <button
                      type="button"
                      aria-label={`${formatTime(segment.start_sec)} 세그먼트 재생`}
                      onClick={() => seekTo(segment.start_sec)}
                      className="focus-ring shrink-0 rounded-lg bg-white px-3 py-1.5 text-xs font-bold text-moss shadow-sm"
                    >
                      ▶ 재생
                    </button>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-ink/75">{segment.text}</p>
                </div>
              ))}
              {filteredSegments.length === 0 && <p className="py-12 text-center text-sm text-ink/45">검색 결과가 없습니다.</p>}
            </div>
          </div>
        </section>

        <section className="min-w-0">
          <div className="rounded-[1.5rem] bg-moss p-6 text-white shadow-soft sm:p-7">
            <p className="text-xs font-bold tracking-[.18em] text-mint">SERMON SUMMARY</p>
            <h1 className="serif mt-3 text-2xl font-bold leading-snug">{results.sermon_summary}</h1>
            <div className="mt-5 flex flex-wrap gap-2">{results.sermon_topics.map((topic) => <span key={topic} className="rounded-full bg-white/10 px-3 py-1 text-xs">#{topic}</span>)}</div>
          </div>

          <div className="mt-5 space-y-5">
            {results.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                projectId={project.project_id}
                analysisMode={results.analysis_mode}
                active={candidate.id === activeCandidateId}
                onPreview={() => preview(candidate)}
              />
            ))}
          </div>
          {results.debug && <DebugPanel debug={results.debug} />}
        </section>
      </div>
    </main>
  );
}

function CandidateCard({
  candidate,
  projectId,
  analysisMode,
  active,
  onPreview,
}: {
  candidate: Candidate;
  projectId: string;
  analysisMode: CandidateResults["analysis_mode"];
  active: boolean;
  onPreview: () => void;
}) {
  const [selectedTitleOrder, setSelectedTitleOrder] = useState<number | null>(null);

  return (
    <article onClick={onPreview} className={`cursor-pointer rounded-[1.5rem] border bg-white/80 p-5 shadow-soft transition sm:p-6 ${active ? "border-moss ring-4 ring-mint" : "border-white hover:-translate-y-0.5 hover:border-moss/25"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3"><span className="serif grid h-10 w-10 place-items-center rounded-full bg-mint text-lg font-bold text-moss">{candidate.candidate_order}</span><div><span className="text-xs font-bold text-gold">{candidate.recommendation_type}</span><h2 className="mt-0.5 text-lg font-bold">{candidate.main_topic}</h2></div></div>
        <div className="shrink-0 text-right"><span className="serif text-2xl font-bold text-moss">{candidate.scores.overall}</span><span className="text-xs text-ink/40"> / 100</span></div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs font-bold"><span className="rounded-lg bg-ink/5 px-2.5 py-1.5">{formatTime(candidate.start_sec)} → {formatTime(candidate.end_sec)}</span><span className="rounded-lg bg-ink/5 px-2.5 py-1.5">{Math.round(candidate.duration_sec)}초</span></div>
      <div className="mt-4 rounded-xl bg-cream/80 p-4">
        <p className="mb-1 text-[11px] font-bold text-ink/45">{analysisMode === "mock" ? "Mock 샘플 대본" : "실제 전사 원문"}</p>
        <p className="line-clamp-4 text-sm leading-6 text-ink/70">“{candidate.transcript}”</p>
      </div>
      <p className="mt-4 text-sm leading-6 text-ink/60"><strong className="text-ink">선정 이유</strong> · {candidate.selection_reason}</p>
      <div className="mt-4 grid grid-cols-4 gap-2">{[
        ["핵심", candidate.scores.centrality], ["완결", candidate.scores.standalone], ["후킹", candidate.scores.hook], ["울림", candidate.scores.emotional_impact],
      ].map(([label, score]) => <div key={String(label)} className="rounded-xl bg-mint/40 px-2 py-2 text-center"><p className="text-[10px] text-ink/45">{label}</p><p className="mt-0.5 text-sm font-bold text-moss">{score}</p></div>)}</div>
      <fieldset className="mt-5 border-t border-ink/10 pt-4" onClick={(event) => event.stopPropagation()}>
        <legend className="text-xs font-bold tracking-wide text-ink/45">추천 제목</legend>
        <div className="mt-2 space-y-2">
          {candidate.titles.map((title) => (
            <label key={title.title_order} className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm transition ${selectedTitleOrder === title.title_order ? "bg-gold/10 ring-1 ring-gold/40" : "hover:bg-ink/[.03]"}`}>
              <input
                type="radio"
                name={`candidate-${candidate.id}-title`}
                aria-label={`${candidate.candidate_order}번 후보 제목: ${title.title}`}
                checked={selectedTitleOrder === title.title_order}
                onChange={() => setSelectedTitleOrder(title.title_order)}
                className="h-4 w-4 shrink-0 accent-[#a77a20]"
              />
              <span className="shrink-0 rounded-md bg-gold/15 px-2 py-0.5 text-[11px] font-bold text-[#956b18]">{title.title_type}</span>
              <span>{title.title}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        <button onClick={(event) => { event.stopPropagation(); onPreview(); }} className="focus-ring w-full rounded-xl bg-ink px-4 py-3 text-sm font-bold text-white">{active ? "원문 검수 중" : "원문 검수 ▶"}</button>
        <CandidateEditButton projectId={projectId} candidateId={candidate.id} selectedTitleOrder={selectedTitleOrder} />
      </div>
    </article>
  );
}

function DebugPanel({ debug }: { debug: NonNullable<CandidateResults["debug"]> }) {
  return (
    <details className="mt-5 rounded-2xl border border-dashed border-ink/20 bg-white/60 p-5 text-xs text-ink/65">
      <summary className="cursor-pointer font-bold text-ink">개발용 전사 디버그 정보</summary>
      <dl className="mt-4 grid grid-cols-2 gap-3">
        <div><dt>분석 모드</dt><dd className="font-bold">{debug.analysis_mode}</dd></div>
        <div><dt>전사 모델</dt><dd className="font-bold">{debug.transcription_model ?? "-"}</dd></div>
        <div><dt>세그먼트</dt><dd className="font-bold">{debug.transcript_segment_count}개</dd></div>
        <div><dt>전체 글자</dt><dd className="font-bold">{debug.transcript_char_count}자</dd></div>
      </dl>
      {debug.first_segment && <p className="mt-3">첫 세그먼트 #{debug.first_segment.segment_id} · {formatTime(debug.first_segment.start_sec)} · {debug.first_segment.text}</p>}
      {debug.last_segment && <p className="mt-2">마지막 세그먼트 #{debug.last_segment.segment_id} · {formatTime(debug.last_segment.end_sec)} · {debug.last_segment.text}</p>}
      <ul className="mt-3 space-y-1">
        {debug.candidates.map((candidate) => (
          <li key={candidate.candidate_order}>
            <p>후보 {candidate.candidate_order}: #{candidate.start_segment_id} → #{candidate.end_segment_id} · {candidate.segment_count}개 · Shorts {candidate.shorts_score ?? "-"}</p>
            <p className="mt-1 text-[11px]">훅 {candidate.hook_strength ?? "-"} · 일반 공감 {candidate.universal_relevance ?? "-"} · 궁금증 {candidate.curiosity_gap ?? "-"} · 결론 {candidate.payoff_strength ?? "-"} · 완결 {candidate.standalone_clarity ?? "-"} · 감정 {candidate.emotional_intensity ?? "-"} · 효율 {candidate.brevity_efficiency ?? "-"}</p>
            <p className="mt-1 text-[11px]">첫 3초 {candidate.opening_3s_score ?? "-"} · 스크롤 정지 {candidate.scroll_stop_score ?? "-"} · 비기독교 이해 {candidate.non_christian_clarity_score ?? "-"} · 제목 가능성 {candidate.title_potential_score ?? "-"} · 밀도 {candidate.information_density_score ?? "-"} · 맥락 {candidate.context_integrity === false ? "fail" : "pass"}{candidate.emotional_triggers?.length ? ` · ${candidate.emotional_triggers.join(", ")}` : ""}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
