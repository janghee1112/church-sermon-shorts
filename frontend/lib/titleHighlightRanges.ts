import type { TitleHighlightRange } from "@/types";

export interface TitleToken {
  id: string;
  text: string;
  start: number;
  end: number;
  lineIndex: number;
}

export interface HighlightSegment {
  text: string;
  highlight: boolean;
  start: number;
  end: number;
}

export type TokenHighlightState = "none" | "full" | "partial";

export function titleCodePoints(title: string): string[] {
  return Array.from(title);
}

export function normalizeHighlightRanges(title: string, ranges: readonly TitleHighlightRange[]): TitleHighlightRange[] {
  const characters = titleCodePoints(title);
  const valid = (ranges ?? [])
    .filter(({ start, end }) => Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= characters.length)
    .filter(({ start, end }) => characters.slice(start, end).join("").trim().length > 0)
    .map(({ start, end }) => ({ start, end }))
    .sort((left, right) => left.start - right.start || left.end - right.end);

  const merged: TitleHighlightRange[] = [];
  for (const range of valid) {
    const previous = merged.at(-1);
    if (previous && range.start <= previous.end) {
      previous.end = Math.max(previous.end, range.end);
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}

export function tokenizeTitle(title: string): TitleToken[] {
  const characters = titleCodePoints(title);
  const tokens: TitleToken[] = [];
  let tokenStart: number | null = null;
  let lineIndex = 0;
  let tokenLineIndex = 0;

  const closeToken = (end: number) => {
    if (tokenStart === null) return;
    tokens.push({
      id: `token-${tokenStart}-${end}`,
      text: characters.slice(tokenStart, end).join(""),
      start: tokenStart,
      end,
      lineIndex: tokenLineIndex,
    });
    tokenStart = null;
  };

  characters.forEach((character, index) => {
    if (/\s/u.test(character)) {
      closeToken(index);
      if (character === "\n") lineIndex += 1;
      return;
    }
    if (tokenStart === null) {
      tokenStart = index;
      tokenLineIndex = lineIndex;
    }
  });
  closeToken(characters.length);
  return tokens;
}

export function getTokenHighlightState(token: TitleToken, ranges: readonly TitleHighlightRange[]): TokenHighlightState {
  const intersections = ranges
    .map((range) => ({ start: Math.max(token.start, range.start), end: Math.min(token.end, range.end) }))
    .filter((range) => range.end > range.start);
  if (!intersections.length) return "none";
  const covered = intersections.reduce((total, range) => total + range.end - range.start, 0);
  return covered >= token.end - token.start ? "full" : "partial";
}

export function replaceTokenHighlight(
  title: string,
  ranges: readonly TitleHighlightRange[],
  token: TitleToken,
  localRange: TitleHighlightRange | null,
): TitleHighlightRange[] {
  const retained = ranges.flatMap((range) => {
    if (range.end <= token.start || range.start >= token.end) return [{ ...range }];
    const pieces: TitleHighlightRange[] = [];
    if (range.start < token.start) pieces.push({ start: range.start, end: token.start });
    if (range.end > token.end) pieces.push({ start: token.end, end: range.end });
    return pieces;
  });
  if (localRange) {
    retained.push({ start: token.start + localRange.start, end: token.start + localRange.end });
  }
  return normalizeHighlightRanges(title, retained);
}

export function splitTitleIntoHighlightSegments(title: string, ranges: readonly TitleHighlightRange[]): HighlightSegment[] {
  const characters = titleCodePoints(title);
  const normalized = normalizeHighlightRanges(title, ranges);
  if (!normalized.length) return title ? [{ text: title, highlight: false, start: 0, end: characters.length }] : [];
  const boundaries = new Set<number>([0, characters.length]);
  normalized.forEach(({ start, end }) => { boundaries.add(start); boundaries.add(end); });
  const ordered = [...boundaries].sort((left, right) => left - right);
  return ordered.slice(0, -1).map((start, index) => {
    const end = ordered[index + 1];
    return {
      text: characters.slice(start, end).join(""),
      highlight: normalized.some((range) => range.start <= start && start < range.end),
      start,
      end,
    };
  }).filter((segment) => segment.text.length > 0);
}
