import type { CleanupStore, HistoryEntry } from "./cleanup-repository";
import { buildCleanupReport, daysInRange, planDeletion, type AuditEntry, type CleanupInput, type PhotoFact } from "./safe-days";

const at = (day: string) => new Date(`${day}T12:00:00Z`);

/** Sample data covering every outcome of the Safe Day rules, for trying the cleanup page offline. */
export function sampleInput(): CleanupInput {
  const photos: PhotoFact[] = [];
  const originalNames = new Set<string>();
  const add = (day: string, count: number, withOriginal = true) => {
    for (let i = 0; i < count; i++) {
      const filename = `IMG_${day.replace(/-/g, "")}_${i}.jpg`;
      photos.push({ id: `${day}-${i}`, filename, takenAt: at(day), originalGcsPath: `${day}-${i}_${filename}` });
      if (withOriginal) originalNames.add(`${day}-${i}_${filename}`);
    }
  };

  daysInRange("2026-03-01", "2026-03-05").forEach((d) => add(d, 3)); // safe, a week of days
  add("2026-03-09", 2); // safe, after a gap with no media
  add("2026-04-02", 2, false); // an Original is missing
  daysInRange("2026-05-10", "2026-05-12").forEach((d) => add(d, 2)); // safe, but a failed file sits near 05-11
  add("2026-10-04", 4); // safe: the day before the export
  add("2026-10-06", 3); // taken after the export
  add("2024-08-15", 5); // 2024 is in no export

  return {
    photos,
    originalNames,
    exports: [{ id: "20261005T232735Z", exportedAt: new Date("2026-10-05T23:27:35Z"), years: [2025, 2026] }],
    problems: [
      { kind: "failed", path: "Takeout/Google Photos/Photos from 2026/IMG_X.jpg", reason: "OSError: boom", takenAt: at("2026-05-12") },
      { kind: "no_sidecar", path: "Takeout/Google Photos/Photos from 2026/IMG_1-edited.jpg", reason: "No Sidecar found", takenAt: null },
    ],
    deletedDays: new Set(),
  };
}

/** In-memory CleanupStore for the demo mode; changes live until the server restarts. */
export class FakeCleanupStore implements CleanupStore {
  private input = sampleInput();
  private deleted = new Set<string>();
  private log = new Map<string, { markedAt: Date; entry: AuditEntry }>();

  static shared(): FakeCleanupStore {
    const g = globalThis as { __fakeCleanupStore?: FakeCleanupStore };
    return (g.__fakeCleanupStore ??= new FakeCleanupStore());
  }

  private current(): CleanupInput {
    return { ...this.input, deletedDays: this.deleted };
  }

  async report() {
    const history: HistoryEntry[] = [...this.log.entries()]
      .map(([id, { markedAt, entry }]) => ({ id, start: entry.start, end: entry.end, itemCount: entry.itemCount, markedAt: markedAt.toISOString() }))
      .sort((a, b) => b.markedAt.localeCompare(a.markedAt));
    return { ...buildCleanupReport(this.current()), history };
  }

  async markDeleted(start: string, end: string) {
    const plan = planDeletion(this.current(), start, end);
    if (!plan.ok) return plan;
    const logId = `demo-${this.log.size + 1}`;
    this.log.set(logId, { markedAt: new Date(), entry: plan.entry });
    const days = daysInRange(start, end);
    days.forEach((d) => this.deleted.add(d));
    return { ok: true as const, logId, days: days.length };
  }

  async logEntry(id: string) {
    const found = this.log.get(id);
    if (!found) return null;
    return { id, ...found.entry, marked_at: found.markedAt.toISOString() };
  }
}
