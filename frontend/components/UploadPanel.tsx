"use client";

import { useRef, useState } from "react";
import { formatBytes } from "@/lib/time";

interface Props {
  busy: boolean;
  progress: number;
  error: string | null;
  onSubmit: (file: File) => void;
}

export function UploadPanel({ busy, progress, error, onSubmit }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function acceptFile(candidate?: File) {
    if (candidate) setFile(candidate);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-5 py-8 sm:px-8 sm:py-12">
      <nav className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-moss text-lg text-white">✦</span>
          <span className="serif text-xl font-bold">말씀컷</span>
        </div>
        <span className="rounded-full border border-ink/10 bg-white/60 px-3 py-1.5 text-xs font-semibold text-moss">MVP · Mock 지원</span>
      </nav>

      <section className="my-auto grid items-center gap-12 py-14 lg:grid-cols-[.9fr_1.1fr]">
        <div>
          <p className="mb-5 text-sm font-bold tracking-[.22em] text-moss">SERMON TO SHORTS</p>
          <h1 className="serif text-5xl font-bold leading-[1.12] tracking-[-.04em] sm:text-6xl">
            긴 말씀 속,<br /><span className="text-moss">오래 남을 한 장면</span>
          </h1>
          <p className="mt-7 max-w-lg text-lg leading-8 text-ink/65">
            설교 영상을 올리면 전체 흐름을 읽고, 짧게 나누기 좋은 핵심 구간 네 곳을 실제 발언과 함께 추천합니다.
          </p>
          <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-ink/60">
            <span>✓ 문장별 타임스탬프</span><span>✓ 겹치지 않는 4개 구간</span><span>✓ 즉시 영상 미리보기</span>
          </div>
        </div>

        <div className="rounded-[2rem] border border-white/80 bg-white/75 p-4 shadow-soft backdrop-blur sm:p-7">
          <div
            role="button"
            tabIndex={0}
            aria-label="MP4 영상 선택"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") inputRef.current?.click(); }}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]); }}
            className={`focus-ring cursor-pointer rounded-[1.5rem] border-2 border-dashed px-5 py-16 text-center transition ${dragging ? "border-moss bg-mint/60" : "border-moss/25 bg-cream/60 hover:border-moss/60"}`}
          >
            <input ref={inputRef} data-testid="file-input" className="sr-only" type="file" accept="video/mp4,.mp4" onChange={(event) => acceptFile(event.target.files?.[0])} />
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-mint text-3xl text-moss">↑</div>
            <p className="mt-5 text-lg font-bold">MP4 설교 영상을 놓아주세요</p>
            <p className="mt-2 text-sm text-ink/50">또는 클릭하여 파일 선택</p>
          </div>

          {file && (
            <div className="mt-4 flex items-center gap-3 rounded-2xl bg-mint/55 p-4">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-moss">▶</span>
              <div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{file.name}</p><p className="mt-0.5 text-xs text-ink/50">{formatBytes(file.size)}</p></div>
              <button className="focus-ring rounded-lg px-2 py-1 text-sm text-ink/50" onClick={(event) => { event.stopPropagation(); setFile(null); }} aria-label="선택 해제">×</button>
            </div>
          )}

          {busy && <div className="mt-4 h-2 overflow-hidden rounded-full bg-ink/10"><div className="h-full rounded-full bg-moss transition-all" style={{ width: `${progress}%` }} /></div>}
          {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <button
            disabled={!file || busy}
            onClick={() => file && onSubmit(file)}
            className="focus-ring mt-5 w-full rounded-2xl bg-moss px-5 py-4 font-bold text-white shadow-lg shadow-moss/15 transition hover:bg-[#244b3a] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? `업로드 중 ${progress}%` : "업로드하고 분석 시작"}
          </button>
          <p className="mt-4 text-center text-xs text-ink/45">MP4 · 최대 2GB · 최대 90분</p>
        </div>
      </section>
    </main>
  );
}

