"use client";

import { useState } from "react";
import { formatTime } from "@/lib/time";
import type { DraftSubtitle } from "@/types";

interface Props {
  subtitles: DraftSubtitle[];
  activeSubtitleId: number | null;
  onChange: (id: number, text: string) => void;
  onPlay: (subtitle: DraftSubtitle) => void;
  onSplit: (id: number, splitIndex: number) => Promise<void>;
  onMerge: (firstId: number, secondId: number) => Promise<void>;
  onResetOne: (id: number) => void;
  onResetAll: () => void;
}

export function SubtitleEditor(props: Props) {
  const [splitTarget, setSplitTarget] = useState<number | null>(null);
  const [splitIndex, setSplitIndex] = useState(0);
  const [working, setWorking] = useState(false);

  async function split(subtitle: DraftSubtitle) {
    if (splitTarget !== subtitle.id) {
      const boundary = subtitle.edited_text.search(/\s+/);
      setSplitTarget(subtitle.id);
      setSplitIndex(boundary > 0 ? boundary : Math.max(1, Math.floor(subtitle.edited_text.length / 2)));
      return;
    }
    setWorking(true);
    try { await props.onSplit(subtitle.id, splitIndex); setSplitTarget(null); } finally { setWorking(false); }
  }

  return (
    <section className="rounded-2xl bg-white p-5 shadow-soft">
      <div className="flex items-center justify-between gap-3"><div><h2 className="serif text-xl font-bold">자막 편집</h2><p className="mt-1 text-xs text-ink/50">원문은 보존되며 편집문만 화면에 표시됩니다.</p></div><button type="button" onClick={props.onResetAll} className="focus-ring rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700">전체 원문 복원</button></div>
      <div className="scrollbar-thin mt-4 max-h-[620px] space-y-3 overflow-y-auto pr-1">
        {props.subtitles.map((subtitle, index) => {
          const tooLong = subtitle.edited_text.length > 34;
          const hasTooManyLines = subtitle.edited_text.split("\n").length > 2;
          return <article key={subtitle.id} data-testid={`subtitle-${subtitle.id}`} className={`rounded-xl border p-3 transition ${props.activeSubtitleId === subtitle.id ? "border-gold bg-amber-50 ring-2 ring-gold/20" : "border-ink/10 bg-cream/55"}`}>
            <div className="flex items-center justify-between gap-2"><button type="button" onClick={() => props.onPlay(subtitle)} className="font-mono text-xs font-bold text-moss">▶ {formatTime(subtitle.start_sec)} - {formatTime(subtitle.end_sec)}</button><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${subtitle.is_edited ? "bg-gold/20 text-amber-800" : "bg-ink/5 text-ink/40"}`}>{subtitle.is_edited ? "편집됨" : `#${subtitle.cue_order}`}</span></div>
            <p className="mt-2 text-xs leading-5 text-ink/45">원문 · {subtitle.original_text}</p>
            <textarea aria-label={`자막 ${subtitle.cue_order} 편집`} value={subtitle.edited_text} onChange={(event) => props.onChange(subtitle.id, event.target.value)} rows={2} className="focus-ring mt-2 w-full resize-y rounded-lg border border-ink/10 bg-white px-3 py-2 text-sm leading-5" />
            {(tooLong || hasTooManyLines) && <p className="mt-1 text-[11px] font-bold text-amber-700">{tooLong ? "한 화면에 표시하기에는 자막이 길 수 있습니다. " : ""}{hasTooManyLines ? "세 줄 이상입니다." : ""}</p>}
            {splitTarget === subtitle.id && <div className="mt-2 rounded-lg bg-white p-2"><label className="text-[11px] font-bold text-ink/55">분할 위치 ({splitIndex}/{subtitle.edited_text.length})</label><input aria-label="자막 분할 위치" type="range" min={1} max={Math.max(1, subtitle.edited_text.length - 1)} value={splitIndex} onChange={(event) => setSplitIndex(Number(event.target.value))} className="mt-1 w-full" /><p className="mt-1 grid grid-cols-2 gap-2 text-xs"><span className="rounded bg-mint/50 p-1">{subtitle.edited_text.slice(0, splitIndex)}</span><span className="rounded bg-mint/50 p-1">{subtitle.edited_text.slice(splitIndex)}</span></p></div>}
            <div className="mt-2 flex flex-wrap gap-1.5"><button type="button" disabled={working || subtitle.edited_text.length < 2} onClick={() => void split(subtitle)} className="rounded-md bg-white px-2 py-1.5 text-[11px] font-bold">{splitTarget === subtitle.id ? "이 위치에서 나누기" : "자막 나누기"}</button>{index > 0 && <button type="button" disabled={working} onClick={() => void props.onMerge(props.subtitles[index - 1].id, subtitle.id)} className="rounded-md bg-white px-2 py-1.5 text-[11px] font-bold">이전과 합치기</button>}{index < props.subtitles.length - 1 && <button type="button" disabled={working} onClick={() => void props.onMerge(subtitle.id, props.subtitles[index + 1].id)} className="rounded-md bg-white px-2 py-1.5 text-[11px] font-bold">다음과 합치기</button>}<button type="button" onClick={() => props.onResetOne(subtitle.id)} disabled={!subtitle.is_edited} className="ml-auto rounded-md px-2 py-1.5 text-[11px] font-bold text-moss disabled:opacity-30">이 자막 원문 복원</button></div>
          </article>;
        })}
      </div>
    </section>
  );
}
