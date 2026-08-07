"use client";

import { useMemo, useState } from "react";
import { formatTime } from "@/lib/time";
import type { TranscriptSegment } from "@/types";

interface Props {
  segments: TranscriptSegment[];
  pendingStartId: number;
  pendingEndId: number;
  recommendedStartId: number;
  recommendedEndId: number;
  activeSegmentId: number | null;
  onChange: (startId: number, endId: number) => void;
  onApply: () => void;
  onPlay: (startSec: number, endSec: number) => void;
}

export function TranscriptRangeSelector(props: Props) {
  const [showAll, setShowAll] = useState(false);
  const startIndex = props.segments.findIndex((item) => item.id === props.pendingStartId);
  const endIndex = props.segments.findIndex((item) => item.id === props.pendingEndId);
  const visible = useMemo(() => {
    if (showAll || startIndex < 0 || endIndex < 0) return props.segments;
    return props.segments.slice(Math.max(0, startIndex - 5), Math.min(props.segments.length, endIndex + 6));
  }, [showAll, startIndex, endIndex, props.segments]);
  const start = props.segments[startIndex];
  const end = props.segments[endIndex];
  const duration = start && end ? end.end_sec - start.start_sec : 0;

  function setStart(id: number) {
    const index = props.segments.findIndex((item) => item.id === id);
    if (index <= endIndex) props.onChange(id, props.pendingEndId);
  }

  function setEnd(id: number) {
    const index = props.segments.findIndex((item) => item.id === id);
    if (index >= startIndex) props.onChange(props.pendingStartId, id);
  }

  return (
    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="serif text-xl font-bold">영상 구간 선택</h2><p className="mt-1 text-xs text-ink/50">문장 경계를 시작·끝으로 지정하세요.</p></div>
        <div className="text-right"><p className={`font-mono text-sm font-bold ${duration < 30 || duration > 75 ? "text-amber-700" : "text-moss"}`}>{formatTime(start?.start_sec ?? 0)} → {formatTime(end?.end_sec ?? 0)}</p><p className="text-xs text-ink/45">{duration.toFixed(1)}초 · {duration < 30 ? "메시지가 충분히 전달되지 않을 수 있습니다." : duration > 75 ? "쇼츠로 사용하기에는 다소 길 수 있습니다." : "적정 길이"}</p></div>
      </div>
      <div className="scrollbar-thin mt-4 max-h-72 space-y-2 overflow-y-auto pr-1">
        {visible.map((segment) => {
          const index = props.segments.findIndex((item) => item.id === segment.id);
          const selected = index >= startIndex && index <= endIndex;
          return <div key={segment.id} data-testid={`range-segment-${segment.id}`} className={`rounded-xl border p-3 ${segment.id === props.activeSegmentId ? "border-gold bg-amber-50 ring-2 ring-gold/20" : selected ? "border-moss/30 bg-mint/60" : "border-ink/10 bg-cream/60"}`}>
            <div className="flex items-center justify-between gap-2"><button type="button" onClick={() => props.onPlay(segment.start_sec, segment.end_sec)} className="font-mono text-xs font-bold text-moss">▶ {formatTime(segment.start_sec)} - {formatTime(segment.end_sec)}</button><div className="flex gap-1"><button type="button" onClick={() => setStart(segment.id)} className={`rounded-md px-2 py-1 text-[11px] font-bold ${segment.id === props.pendingStartId ? "bg-moss text-white" : "bg-white"}`}>시작으로 설정</button><button type="button" onClick={() => setEnd(segment.id)} className={`rounded-md px-2 py-1 text-[11px] font-bold ${segment.id === props.pendingEndId ? "bg-moss text-white" : "bg-white"}`}>종료로 설정</button></div></div>
            <p className="mt-1 text-sm leading-5 text-ink/70">{segment.text}</p>
          </div>;
        })}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={() => setShowAll((value) => !value)} className="focus-ring rounded-lg border border-ink/10 bg-white px-3 py-2 text-xs font-bold">{showAll ? "주변 문장만" : "전체 대본에서 보기"}</button>
        <button type="button" onClick={() => props.onChange(props.recommendedStartId, props.recommendedEndId)} className="focus-ring rounded-lg border border-ink/10 bg-white px-3 py-2 text-xs font-bold">AI 추천 구간으로 되돌리기</button>
        <button type="button" onClick={props.onApply} disabled={!start || !end} className="focus-ring ml-auto rounded-lg bg-moss px-4 py-2 text-xs font-bold text-white disabled:opacity-40">변경한 구간 적용</button>
      </div>
    </section>
  );
}
