/**
 * Which days of the Photo Index can be deleted from Google Photos. A day is "safe" when everything
 * Google Photos holds for it is known to be in the originals bucket (see Safe Day in CONTEXT.md).
 * Days are UTC dates of `taken_at`; the ±1 day margin on problems covers the gap from local dates.
 */

export interface PhotoFact {
  takenAt: Date;
  originalGcsPath?: string | null;
  youtubeVideoId?: string | null;
}

export interface ExportFact {
  exportedAt: Date;
  years: number[];
}

export interface ProblemFact {
  kind: string;
  path: string;
  reason: string;
  takenAt: Date | null;
}

export type UnsafeReason = "not_covered" | "after_export" | "problem_nearby" | "original_missing";

export interface SafeRange {
  start: string; // YYYY-MM-DD
  end: string;
  itemCount: number;
}

export interface UnsafeDay {
  day: string;
  itemCount: number;
  reasons: UnsafeReason[];
}

export interface CleanupReport {
  safeRanges: SafeRange[]; // newest first
  unsafeDays: UnsafeDay[]; // newest first
  undatedProblems: ProblemFact[];
  deletedDays: string[];
}

export interface CleanupInput {
  photos: PhotoFact[];
  exports: ExportFact[];
  /** Problems not resolved yet. */
  problems: ProblemFact[];
  /** Every object name in the originals bucket. */
  originalNames: ReadonlySet<string>;
  /** Days already marked deleted in Google Photos (YYYY-MM-DD). */
  deletedDays: ReadonlySet<string>;
}

const DAY_MS = 24 * 60 * 60 * 1000;

export function dayOf(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function dayNumber(day: string): number {
  return Date.parse(`${day}T00:00:00Z`) / DAY_MS;
}

export function daysInRange(start: string, end: string): string[] {
  const days: string[] = [];
  for (let n = dayNumber(start); n <= dayNumber(end); n++) days.push(dayOf(new Date(n * DAY_MS)));
  return days;
}

export function buildCleanupReport(input: CleanupInput): CleanupReport {
  const itemsByDay = new Map<string, PhotoFact[]>();
  for (const photo of input.photos) {
    const day = dayOf(photo.takenAt);
    if (!itemsByDay.has(day)) itemsByDay.set(day, []);
    itemsByDay.get(day)!.push(photo);
  }

  const problemDays = input.problems.filter((p) => p.takenAt).map((p) => dayNumber(dayOf(p.takenAt!)));
  const undatedProblems = input.problems.filter((p) => !p.takenAt);

  const safeRanges: SafeRange[] = [];
  const unsafeDays: UnsafeDay[] = [];
  let current: SafeRange | null = null;

  // Oldest first, so a range grows forward. Days without media aren't visited, so they don't break
  // a range. A day already marked deleted has nothing left in Photos to protect, and doesn't either.
  for (const day of [...itemsByDay.keys()].sort()) {
    if (input.deletedDays.has(day)) continue;
    const items = itemsByDay.get(day)!;
    const reasons = unsafeReasons(day, items, input, problemDays);
    if (reasons.length === 0) {
      if (current) {
        current.end = day;
        current.itemCount += items.length;
      } else {
        current = { start: day, end: day, itemCount: items.length };
        safeRanges.push(current);
      }
    } else {
      current = null;
      unsafeDays.push({ day, itemCount: items.length, reasons });
    }
  }

  return {
    safeRanges: safeRanges.reverse(),
    unsafeDays: unsafeDays.reverse(),
    undatedProblems,
    deletedDays: [...input.deletedDays].sort().reverse(),
  };
}

function unsafeReasons(
  day: string,
  items: PhotoFact[],
  input: CleanupInput,
  problemDays: number[]
): UnsafeReason[] {
  const reasons: UnsafeReason[] = [];
  const year = Number(day.slice(0, 4));

  const covering = input.exports.filter((e) => e.years.includes(year));
  if (covering.length === 0) reasons.push("not_covered");
  else if (!covering.some((e) => day < dayOf(e.exportedAt))) reasons.push("after_export");

  const n = dayNumber(day);
  if (problemDays.some((p) => Math.abs(p - n) <= 1)) reasons.push("problem_nearby");

  const missing = items.some(
    (item) => !item.youtubeVideoId && !(item.originalGcsPath && input.originalNames.has(item.originalGcsPath))
  );
  if (missing) reasons.push("original_missing");

  return reasons;
}
