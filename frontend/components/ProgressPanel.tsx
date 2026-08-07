import type { Project, ProjectStatus } from "@/types";

const stages: Array<{ key: ProjectStatus; label: string; note: string }> = [
  { key: "uploaded", label: "영상 업로드", note: "원본과 메타데이터 확인" },
  { key: "extracting_audio", label: "음성 추출", note: "16kHz 단일 채널로 변환" },
  { key: "transcribing", label: "대본 생성", note: "한국어 음성과 시간 연결" },
  { key: "analyzing", label: "핵심 구간 분석", note: "완결성과 후킹력 평가" },
  { key: "completed", label: "추천 완성", note: "서로 겹치지 않는 4개 구간" },
];

const order: ProjectStatus[] = ["uploaded", "extracting_audio", "transcribing", "analyzing", "completed"];

export function ProgressPanel({ project, onRetry }: { project: Project; onRetry: () => void }) {
  const currentIndex = order.indexOf(project.status === "failed" ? ((project.error_stage as ProjectStatus) ?? "uploaded") : project.status);
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl items-center px-5 py-12">
      <section className="w-full rounded-[2rem] border border-white bg-white/80 p-7 shadow-soft sm:p-10">
        <div className="flex items-start justify-between gap-5">
          <div><p className="text-xs font-bold tracking-[.2em] text-moss">ANALYZING SERMON</p><h1 className="serif mt-2 text-3xl font-bold">말씀의 흐름을 읽고 있어요</h1></div>
          <span className="rounded-full bg-mint px-4 py-2 text-sm font-bold text-moss">{project.progress}%</span>
        </div>
        <p className="mt-4 truncate text-sm text-ink/55">{project.original_file_name}</p>
        <div className="mt-7 h-3 overflow-hidden rounded-full bg-ink/10"><div className="h-full rounded-full bg-gradient-to-r from-moss to-gold transition-all duration-700" style={{ width: `${project.progress}%` }} /></div>

        <div className="mt-9 space-y-2">
          {stages.map((stage, index) => {
            const done = index < currentIndex;
            const active = index === currentIndex && project.status !== "failed";
            return (
              <div key={stage.key} className={`flex gap-4 rounded-2xl p-4 ${active ? "bg-mint/60" : ""}`}>
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${done ? "bg-moss text-white" : active ? "border-2 border-moss text-moss" : "bg-ink/5 text-ink/35"}`}>{done ? "✓" : index + 1}</span>
                <div><p className={`font-bold ${!done && !active ? "text-ink/35" : ""}`}>{stage.label}</p><p className="mt-0.5 text-sm text-ink/45">{stage.note}</p></div>
              </div>
            );
          })}
        </div>

        {project.status === "failed" && (
          <div className="mt-7 rounded-2xl border border-red-200 bg-red-50 p-5">
            <p className="font-bold text-red-800">분석을 완료하지 못했습니다</p>
            <p role="alert" className="mt-1 text-sm leading-6 text-red-700">{project.error_message}</p>
            <button onClick={onRetry} className="focus-ring mt-4 rounded-xl bg-red-700 px-4 py-2.5 text-sm font-bold text-white">다시 시도</button>
          </div>
        )}
        <p className="mt-7 text-center text-xs text-ink/40">영상 길이에 따라 몇 분 정도 걸릴 수 있습니다. 이 화면을 열어두지 않아도 상태는 저장됩니다.</p>
      </section>
    </main>
  );
}
