"use client";

import { useEffect, useRef, useState } from "react";
import type { TitleHighlightRange } from "@/types";
import {
  getTokenHighlightState,
  normalizeHighlightRanges,
  replaceTokenHighlight,
  titleCodePoints,
  tokenizeTitle,
  type TitleToken,
} from "@/lib/titleHighlightRanges";

interface DetailDialogProps {
  title: string;
  token: TitleToken;
  ranges: readonly TitleHighlightRange[];
  onApply: (ranges: TitleHighlightRange[]) => void;
  onClose: () => void;
}

function tokenLocalRange(token: TitleToken, ranges: readonly TitleHighlightRange[]): TitleHighlightRange | null {
  const overlap = ranges.find((range) => range.start < token.end && range.end > token.start);
  return overlap
    ? { start: Math.max(0, overlap.start - token.start), end: Math.min(token.end, overlap.end) - token.start }
    : null;
}

function TitleHighlightDetailDialog({ title, token, ranges, onApply, onClose }: DetailDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const characters = titleCodePoints(token.text);
  const [selection, setSelection] = useState<TitleHighlightRange | null>(() => tokenLocalRange(token, ranges));
  const [anchor, setAnchor] = useState<number | null>(null);

  useEffect(() => {
    dialogRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const selectedText = selection ? characters.slice(selection.start, selection.end).join("") : "없음";

  function selectCharacter(index: number) {
    if (anchor === null) {
      setAnchor(index);
      setSelection({ start: index, end: index + 1 });
      return;
    }
    setSelection({ start: Math.min(anchor, index), end: Math.max(anchor, index) + 1 });
    setAnchor(null);
  }

  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="title-highlight-dialog-title" tabIndex={-1} className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl outline-none">
      <h3 id="title-highlight-dialog-title" className="serif text-xl font-bold">어절 세부 강조</h3>
      <p className="mt-1 text-sm text-ink/55">어절: <strong className="text-ink">{token.text}</strong></p>
      <p className="mt-3 rounded-lg bg-cream px-3 py-2 text-sm">현재 선택: <strong>{selectedText}</strong></p>
      <p className="mt-4 text-xs font-bold text-ink/55">첫 글자와 마지막 글자를 차례로 선택하세요.</p>
      <div className="mt-2 flex flex-wrap gap-2" aria-label={`${token.text} 글자 범위 선택`}>
        {characters.map((character, index) => {
          const selected = Boolean(selection && selection.start <= index && index < selection.end);
          return <button key={`${index}-${character}`} type="button" aria-pressed={selected} aria-label={`${character}, ${selected ? "강조 선택됨" : "강조 선택 안 됨"}`} onClick={() => selectCharacter(index)} className={`focus-ring min-w-10 rounded-lg border px-3 py-2 text-lg font-bold ${selected ? "border-amber-500 bg-amber-200 text-amber-950" : "border-ink/15 bg-white"}`}>{character}</button>;
        })}
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button type="button" onClick={() => { setSelection({ start: 0, end: characters.length }); setAnchor(null); }} className="focus-ring rounded-lg bg-cream px-3 py-2 text-sm font-bold">전체 선택</button>
        <button type="button" onClick={() => onApply(replaceTokenHighlight(title, ranges, token, null))} className="focus-ring rounded-lg border border-red-200 px-3 py-2 text-sm font-bold text-red-700">강조 해제</button>
        <span className="flex-1" />
        <button type="button" onClick={onClose} className="focus-ring rounded-lg border border-ink/15 px-3 py-2 text-sm font-bold">취소</button>
        <button type="button" disabled={!selection} onClick={() => selection && onApply(replaceTokenHighlight(title, ranges, token, selection))} className="focus-ring rounded-lg bg-moss px-4 py-2 text-sm font-bold text-white disabled:opacity-40">적용</button>
      </div>
    </div>
  </div>;
}

interface Props {
  title: string;
  ranges: readonly TitleHighlightRange[];
  onChange: (ranges: TitleHighlightRange[]) => void;
}

export function TitleHighlightEditor({ title, ranges, onChange }: Props) {
  const normalized = normalizeHighlightRanges(title, ranges);
  const tokens = tokenizeTitle(title);
  const [activeToken, setActiveToken] = useState<TitleToken | null>(null);
  const returnFocusRef = useRef<HTMLButtonElement | null>(null);
  const lineIndexes = [...new Set(tokens.map((token) => token.lineIndex))];

  function closeDialog() {
    setActiveToken(null);
    window.setTimeout(() => returnFocusRef.current?.focus(), 0);
  }

  function openDialog(token: TitleToken, button: HTMLButtonElement) {
    returnFocusRef.current = button;
    setActiveToken(token);
  }

  return <div className="mt-4">
    <div className="flex items-center justify-between gap-3">
      <p className="text-xs font-bold text-ink/60">노란색으로 강조할 부분</p>
      {normalized.length > 0 && <button type="button" onClick={() => onChange([])} className="focus-ring rounded-md px-2 py-1 text-xs font-bold text-red-700">전체 강조 초기화</button>}
    </div>
    {!tokens.length && <p className="mt-2 rounded-lg bg-cream/70 px-3 py-2 text-xs text-ink/45">큰 제목을 입력하면 어절 선택 버튼이 표시됩니다.</p>}
    <div className="mt-2 space-y-2">
      {lineIndexes.map((lineIndex) => <div key={lineIndex} className="flex flex-wrap gap-2" data-testid={`title-token-line-${lineIndex}`}>
        {tokens.filter((token) => token.lineIndex === lineIndex).map((token) => {
          const state = getTokenHighlightState(token, normalized);
          const stateText = state === "full" ? "전체 강조됨" : state === "partial" ? "일부 글자 강조됨" : "강조 안 됨";
          return <span key={token.id} className="inline-flex items-stretch">
            <button
              type="button"
              aria-pressed={state !== "none"}
              aria-label={`${token.text}, ${stateText}`}
              data-highlight-state={state}
              onClick={(event) => state === "none"
                ? onChange(normalizeHighlightRanges(title, [...normalized, { start: token.start, end: token.end }]))
                : openDialog(token, event.currentTarget)}
              className={`focus-ring rounded-l-lg border px-3 py-2 text-sm font-bold ${state === "full" ? "border-amber-500 bg-amber-200 text-amber-950" : state === "partial" ? "border-amber-500 bg-amber-50 text-amber-900" : "rounded-r-lg border-ink/15 bg-white"}`}
            >{state !== "none" && <span aria-hidden="true">✓ </span>}{token.text}</button>
            {state !== "none" && <button type="button" aria-label={`${token.text} 강조 해제`} onClick={() => onChange(replaceTokenHighlight(title, normalized, token, null))} className="focus-ring rounded-r-lg border border-l-0 border-amber-500 bg-amber-100 px-2 font-black text-amber-950">×</button>}
          </span>;
        })}
      </div>)}
    </div>
    {activeToken && <TitleHighlightDetailDialog title={title} token={activeToken} ranges={normalized} onClose={closeDialog} onApply={(next) => { onChange(next); closeDialog(); }} />}
  </div>;
}
