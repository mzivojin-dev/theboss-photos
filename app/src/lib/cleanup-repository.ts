import type { Bucket } from "@google-cloud/storage";
import {
  buildCleanupReport,
  daysInRange,
  planDeletion,
  type CleanupInput,
  type CleanupReport,
  type ExportFact,
  type PhotoFact,
  type ProblemFact,
} from "./safe-days";

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const BATCH_LIMIT = 500;
export const MAX_RANGE_DAYS = 3660;
const HISTORY_LIMIT = 100;

export interface HistoryEntry {
  id: string;
  start: string;
  end: string;
  itemCount: number;
  markedAt: string;
}

/** Firestore timestamps to ISO strings, recursively, for JSON. */
function serialize(value: any): any {
  if (value?.toDate) return value.toDate().toISOString();
  if (Array.isArray(value)) return value.map(serialize);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, serialize(v)]));
  return value;
}

/** What the cleanup routes need; the demo mode (CLEANUP_FAKE_DATA) supplies an in-memory one. */
export interface CleanupStore {
  report(): Promise<CleanupReport & { history: HistoryEntry[] }>;
  markDeleted(start: string, end: string): Promise<{ ok: true; logId: string; days: number } | { ok: false; error: string }>;
  logEntry(id: string): Promise<unknown | null>;
}

/** Reads the Photo Index, the Ingestion Ledger and the originals bucket for the cleanup page. */
export class CleanupRepository implements CleanupStore {
  constructor(private db: FirebaseFirestore.Firestore, private originals: Bucket) {}

  async report(): Promise<CleanupReport & { history: HistoryEntry[] }> {
    const [input, history] = await Promise.all([this.load(), this.history()]);
    return { ...buildCleanupReport(input), history };
  }

  /**
   * Marks every day from `start` to `end` (YYYY-MM-DD, inclusive) as deleted in Google Photos. The range is
   * re-checked first, and an immutable audit entry (`cleanup_log`) is written before the days are marked,
   * so a day is never marked without a record of why it was safe.
   */
  async markDeleted(start: string, end: string): Promise<{ ok: true; logId: string; days: number } | { ok: false; error: string }> {
    const plan = planDeletion(await this.load(), start, end);
    if (!plan.ok) return plan;
    const { items, ...summary } = plan.entry;
    const now = new Date();

    const logRef = this.db.collection("cleanup_log").doc();
    await logRef.set({
      ...summary,
      exports: summary.exports.map((e) => ({ id: e.id, exported_at: e.exportedAt, years: e.years })),
      marked_at: now,
      item_chunks: Math.ceil(items.length / BATCH_LIMIT),
    });
    for (let i = 0; i < items.length; i += BATCH_LIMIT) {
      await logRef.collection("items").doc(String(i / BATCH_LIMIT).padStart(5, "0")).set({ items: items.slice(i, i + BATCH_LIMIT) });
    }

    const days = daysInRange(start, end);
    for (let i = 0; i < days.length; i += BATCH_LIMIT) {
      const batch = this.db.batch();
      for (const day of days.slice(i, i + BATCH_LIMIT)) {
        batch.set(this.db.collection("cleanup_days").doc(day), { day, deleted_at: now, log_id: logRef.id });
      }
      await batch.commit();
    }
    return { ok: true, logId: logRef.id, days: days.length };
  }

  /** One audit entry with every item in it, or null. */
  async logEntry(id: string) {
    const ref = this.db.collection("cleanup_log").doc(id);
    const [doc, chunks] = await Promise.all([ref.get(), ref.collection("items").orderBy("__name__").get()]);
    if (!doc.exists) return null;
    return { id, ...serialize(doc.data()!), items: chunks.docs.flatMap((c) => c.data().items) };
  }

  private async load(): Promise<CleanupInput> {
    const [photos, exports, problems, deletedDays, originalNames] = await Promise.all([
      this.photos(),
      this.exports(),
      this.problems(),
      this.deletedDays(),
      this.originalNames(),
    ]);
    return { photos, exports, problems, originalNames, deletedDays };
  }

  private async history(): Promise<HistoryEntry[]> {
    const snapshot = await this.db.collection("cleanup_log").orderBy("marked_at", "desc").limit(HISTORY_LIMIT).get();
    return snapshot.docs.map((doc) => {
      const d = doc.data();
      return { id: doc.id, start: d.start, end: d.end, itemCount: d.itemCount, markedAt: d.marked_at.toDate().toISOString() };
    });
  }

  private async photos(): Promise<PhotoFact[]> {
    const snapshot = await this.db
      .collection("photos")
      .select("taken_at", "filename", "original_gcs_path", "youtube_video_id")
      .get();
    return snapshot.docs.map((doc) => {
      const data = doc.data();
      return {
        id: doc.id,
        filename: data.filename ?? "",
        takenAt: data.taken_at.toDate(),
        originalGcsPath: data.original_gcs_path ?? null,
        youtubeVideoId: data.youtube_video_id ?? null,
      };
    });
  }

  private async exports(): Promise<ExportFact[]> {
    const snapshot = await this.db.collection("takeout_exports").get();
    return snapshot.docs
      .filter((doc) => doc.data().exported_at) // an archive not named like an export has no date to compare
      .map((doc) => ({
        id: doc.id,
        exportedAt: doc.data().exported_at.toDate(),
        years: (doc.data().years ?? []) as number[],
      }));
  }

  private async problems(): Promise<ProblemFact[]> {
    const snapshot = await this.db.collection("takeout_problems").where("resolved_at", "==", null).get();
    return snapshot.docs.map((doc) => {
      const data = doc.data();
      return {
        kind: data.kind,
        path: data.path,
        reason: data.reason,
        takenAt: data.taken_at ? data.taken_at.toDate() : null,
      };
    });
  }

  private async deletedDays(): Promise<Set<string>> {
    const snapshot = await this.db.collection("cleanup_days").select().get();
    return new Set(snapshot.docs.map((doc) => doc.id));
  }

  /** One listing of the bucket's object names: never reads an object (Archive storage charges for that). */
  private async originalNames(): Promise<Set<string>> {
    const [files] = await this.originals.getFiles({ autoPaginate: true, fields: "items(name),nextPageToken" });
    return new Set(files.map((file) => file.name));
  }
}

export function isValidDay(value: unknown): value is string {
  // Re-formatting rejects dates the Date constructor would roll over, such as 2026-02-31.
  return typeof value === "string" && DAY.test(value) && new Date(`${value}T00:00:00Z`).toISOString().startsWith(value);
}
