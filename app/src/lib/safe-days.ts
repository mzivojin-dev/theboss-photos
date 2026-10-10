/**
 * Which days of the Photo Index can be deleted from Google Photos. A day is "safe" when everything
 * Google Photos holds for it is known to be in the originals bucket (see Safe Day in CONTEXT.md).
 * Days are UTC dates of `taken_at`; the ±1 day margin on problems covers the gap from local dates.
 */

export interface PhotoFact {
  id: string;
  filename: string;
  takenAt: Date;
  originalGcsPath?: string | null;
  youtubeVideoId?: string | null;
}

export interface ExportFact {
  id: string;
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

export interface AuditItem {
  id: string;
  filename: string;
  day: string;
  original: string | null;
}

/** What is recorded when a range is marked deleted: the evidence that it was safe at that moment. */
export interface AuditEntry {
  start: string;
  end: string;
  itemCount: number;
  days: Record<string, number>; // items per day
  items: AuditItem[];
  exports: { id: string; exportedAt: Date; years: number[] }[]; // the exports that covered the range's years
  unresolvedProblems: number; // open problems in the whole ledger at that moment
  originalsListed: number; // objects in the originals bucket at that moment
}

export type DeletionPlan = { ok: true; entry: AuditEntry } | { ok: false; error: string };

/**
 * Re-checks a range against the current data before it is marked deleted. The range must lie inside
 * one safe range, so a stale page can't mark a day that has become unsafe since it was loaded.
 */
export function planDeletion(input: CleanupInput, start: string, end: string): DeletionPlan {
  const report = buildCleanupReport(input);
  if (!report.safeRanges.some((r) => r.start <= start && end <= r.end)) {
    return { ok: false, error: "This range is not entirely safe to delete any more; reload the list" };
  }

  const items: AuditItem[] = [];
  const days: Record<string, number> = {};
  for (const photo of input.photos) {
    const day = dayOf(photo.takenAt);
    if (day < start || day > end || input.deletedDays.has(day)) continue;
    days[day] = (days[day] ?? 0) + 1;
    items.push({ id: photo.id, filename: photo.filename, day, original: photo.originalGcsPath ?? null });
  }
  items.sort((a, b) => a.day.localeCompare(b.day) || a.id.localeCompare(b.id));

  const years = new Set(daysInRange(start, end).map((d) => Number(d.slice(0, 4))));
  return {
    ok: true,
    entry: {
      start,
      end,
      itemCount: items.length,
      days,
      items,
      exports: input.exports.filter((e) => e.years.some((y) => years.has(y))).map(({ id, exportedAt, years }) => ({ id, exportedAt, years })),
      unresolvedProblems: input.problems.length,
      originalsListed: input.originalNames.size,
    },
  };
}
