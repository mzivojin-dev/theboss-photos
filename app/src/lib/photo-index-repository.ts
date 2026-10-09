export interface PhotoDoc {
  googlePhotosId: string;
  filename: string;
  takenAt: Date;
  previewGcsPath: string;
  originalGcsPath: string;
  youtubeVideoId?: string;
  width: number;
  height: number;
  latitude: number | null;
  longitude: number | null;
}

export interface PhotoResult {
  id: string;
  takenAt: Date;
  previewGcsPath: string | null;
  originalGcsPath: string;
  youtubeVideoId?: string;
  width: number | null;
  height: number | null;
  /** On a group's cover: how many similar photos it stands for, itself included. */
  groupSize?: number;
}

export interface ListOptions {
  limit: number;
  cursor?: string;
}

export interface ListResult {
  photos: PhotoResult[];
  nextCursor: string | null;
}

export class PhotoIndexRepository {
  constructor(private db: FirebaseFirestore.Firestore) {}

  /**
   * One page of the timeline, newest first. Photos grouped behind a cover (`grouped_under`) are
   * left out, so a group shows as its cover alone. The cursor is the last photo looked at, hidden
   * or not, so the next page carries on from there.
   */
  async list({ limit, cursor }: ListOptions): Promise<ListResult> {
    const photos: PhotoResult[] = [];
    let after = cursor;
    let nextCursor: string | null = null;

    while (photos.length < limit) {
      let query = this.db
        .collection("photos")
        .orderBy("taken_at", "desc")
        .limit(limit);

      if (after) {
        const cursorDoc = await this.db.collection("photos").doc(after).get();
        if (cursorDoc.exists) {
          query = query.startAfter(cursorDoc);
        }
      }

      const snapshot = await query.get();
      for (const doc of snapshot.docs) {
        if (doc.data().grouped_under) continue;
        photos.push(toResult(doc));
      }
      if (snapshot.docs.length < limit) {
        nextCursor = null;
        break;
      }
      after = snapshot.docs[snapshot.docs.length - 1].id;
      nextCursor = after;
    }

    return { photos, nextCursor };
  }

  /** The photos a cover stands for, the cover first, then the rest in the order they were taken. */
  async group(coverId: string): Promise<PhotoResult[]> {
    const [cover, members] = await Promise.all([
      this.db.collection("photos").doc(coverId).get(),
      this.db.collection("photos").where("grouped_under", "==", coverId).get(),
    ]);
    const rest = members.docs
      .map(toResult)
      .sort((a, b) => a.takenAt.getTime() - b.takenAt.getTime());
    return cover.exists ? [toResult(cover), ...rest] : rest;
  }
}

function toResult(doc: FirebaseFirestore.QueryDocumentSnapshot | FirebaseFirestore.DocumentSnapshot): PhotoResult {
  const data = doc.data()!;
  return {
    id: doc.id,
    takenAt: data.taken_at.toDate(),
    previewGcsPath: data.preview_gcs_path ?? null,
    originalGcsPath: data.original_gcs_path,
    youtubeVideoId: data.youtube_video_id ?? undefined,
    width: data.width ?? null,
    height: data.height ?? null,
    groupSize: data.group_size ?? undefined,
  };
}
