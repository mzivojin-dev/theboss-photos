import type { Bucket } from "@google-cloud/storage";
import {
  buildCleanupReport,
  daysInRange,
  type CleanupReport,
  type ExportFact,
  type PhotoFact,
  type ProblemFact,
} from "./safe-days";

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const BATCH_LIMIT = 500;
export const MAX_RANGE_DAYS = 3660;

/** Reads the Photo Index, the Ingestion Ledger and the originals bucket for the cleanup page. */
export class CleanupRepository {
  constructor(private db: FirebaseFirestore.Firestore, private originals: Bucket) {}

  async report(): Promise<CleanupReport> {
    const [photos, exports, problems, deletedDays, originalNames] = await Promise.all([
      this.photos(),
      this.exports(),
      this.problems(),
      this.deletedDays(),
      this.originalNames(),
    ]);
    return buildCleanupReport({ photos, exports, problems, originalNames, deletedDays });
  }

  /** Marks every day from `start` to `end` (YYYY-MM-DD, inclusive) as deleted in Google Photos. */
  async markDeleted(start: string, end: string): Promise<number> {
    const days = daysInRange(start, end);
    const now = new Date();
    for (let i = 0; i < days.length; i += BATCH_LIMIT) {
      const batch = this.db.batch();
      for (const day of days.slice(i, i + BATCH_LIMIT)) {
        batch.set(this.db.collection("cleanup_days").doc(day), { day, deleted_at: now });
      }
      await batch.commit();
    }
    return days.length;
  }

  private async photos(): Promise<PhotoFact[]> {
    const snapshot = await this.db
      .collection("photos")
      .select("taken_at", "original_gcs_path", "youtube_video_id")
      .get();
    return snapshot.docs.map((doc) => {
      const data = doc.data();
      return {
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
