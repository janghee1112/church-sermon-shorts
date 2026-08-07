import type { ReactNode } from "react";
import type { TitleHighlightRange } from "@/types";
import { splitTitleIntoHighlightSegments } from "@/lib/titleHighlightRanges";

export function buildHighlightedTitle(title: string, ranges: readonly TitleHighlightRange[]): ReactNode[] {
  return splitTitleIntoHighlightSegments(title, ranges).map((segment) => segment.highlight
    ? <mark key={`${segment.start}-${segment.end}`} data-testid="title-highlight" className="bg-transparent text-[var(--sermon-highlight)]">{segment.text}</mark>
    : <span key={`${segment.start}-${segment.end}`}>{segment.text}</span>);
}

export function HighlightedTitle({ title, ranges }: { title: string; ranges: readonly TitleHighlightRange[] }) {
  return <>{buildHighlightedTitle(title, ranges)}</>;
}
