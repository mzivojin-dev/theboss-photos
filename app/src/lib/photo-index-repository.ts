export interface PhotoDoc {
  googlePhotosId: string;
  filename: string;
  takenAt: Date;
  previewGcsPath: string;
  originalGcsPath: string;
  width: number;
  height: number;
  latitude: number | null;
  longitude: number | null;
}

export interface PhotoResult {
  id: string;
  takenAt: Date;
  previewGcsPath: string;
  originalGcsPath: string;
  width: number;
  height: number;
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

  async list({ limit, cursor }: ListOptions): Promise<ListResult> {
    let query = this.db
      .collection("photos")
      .orderBy("takenAt", "desc")
      .limit(limit);

    if (cursor) {
      const cursorDoc = await this.db.collection("photos").doc(cursor).get();
      if (cursorDoc.exists) {
        query = query.startAfter(cursorDoc);
      }
    }

    const snapshot = await query.get();
    const photos: PhotoResult[] = snapshot.docs.map((doc) => {
      const data = doc.data();
      return {
        id: doc.id,
        takenAt: data.takenAt.toDate(),
        previewGcsPath: data.previewGcsPath,
        originalGcsPath: data.originalGcsPath,
        width: data.width,
        height: data.height,
      };
    });

    const nextCursor =
      snapshot.docs.length === limit
        ? snapshot.docs[snapshot.docs.length - 1].id
        : null;

    return { photos, nextCursor };
  }
}
