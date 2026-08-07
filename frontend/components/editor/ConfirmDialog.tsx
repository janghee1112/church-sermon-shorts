"use client";

export function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel }: { title: string; message: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void }) {
  return <div role="dialog" aria-modal="true" aria-labelledby="confirm-title" className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-5"><div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"><h2 id="confirm-title" className="serif text-xl font-bold">{title}</h2><p className="mt-3 text-sm leading-6 text-ink/65">{message}</p><div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onCancel} className="focus-ring rounded-lg border border-ink/10 px-4 py-2 text-sm font-bold">취소</button><button type="button" onClick={onConfirm} className="focus-ring rounded-lg bg-moss px-4 py-2 text-sm font-bold text-white">{confirmLabel}</button></div></div></div>;
}
