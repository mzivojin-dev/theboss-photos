import type { TextEmbedding } from "./embed-client";
import { PHOTO_RESULT_FIELDS, toResult, type PhotoResult } from "./photo-index-repository";

/** Firestore returns at most this many neighbours from one vector query. */
const MAX_NEIGHBOURS = 1000;

export interface SearchOptions {
  limit: number;
  /** Only photos taken at or after this instant. */
  from?: Date;
  /** Only photos taken before this instant. */
  to?: Date;
}

/**
 * The photos whose embeddings are nearest the query's, best match first. Only photos embedded with
 * the query's model are compared: while a new model is being rolled out, photos not yet re-embedded
 * are left out rather than matched against a vector from another space.
 * A photo hidden behind a
 * Similar Group's cover is shown as that cover, so a group appears once, as on the Timeline.
 *
 * The date range is applied to the nearest neighbours rather than inside the vector query, so with
 * a range it asks for as many as Firestore allows. Exact while the library has under
 * MAX_NEIGHBOURS embedded photos; beyond that a narrow range can miss matches (see ADR 0003).
 */
export async function searchPhotos(
  db: FirebaseFirestore.Firestore,
  query: TextEmbedding,
  { limit, from, to }: SearchOptions,
): Promise<PhotoResult[]> {
  const dated = Boolean(from || to);
  const snapshot = await db
    .collection("photos")
    .where("embedding_model", "==", query.model)
    .select(...PHOTO_RESULT_FIELDS)
    .findNearest({
      vectorField: "embedding",
      queryVector: query.embedding,
      // Extra neighbours make up for those that collapse into a cover already in the results.
      limit: dated ? MAX_NEIGHBOURS : Math.min(limit * 3, MAX_NEIGHBOURS),
      distanceMeasure: "COSINE",
    })
    .get();

  const ranked: { id: string; doc?: FirebaseFirestore.QueryDocumentSnapshot }[] = [];
  const seen = new Set<string>();
  for (const doc of snapshot.docs) {
    const takenAt: Date = doc.data().taken_at.toDate();
    if ((from && takenAt < from) || (to && takenAt >= to)) continue;
    const coverId: string | undefined = doc.data().grouped_under;
    const id = coverId ?? doc.id;
    if (seen.has(id)) continue;
    seen.add(id);
    ranked.push(coverId ? { id } : { id, doc });
    if (ranked.length === limit) break;
  }

  const coverRefs = ranked.filter((r) => !r.doc).map((r) => db.collection("photos").doc(r.id));
  const covers = new Map<string, FirebaseFirestore.DocumentSnapshot>();
  if (coverRefs.length > 0) {
    for (const cover of await db.getAll(...coverRefs, { fieldMask: PHOTO_RESULT_FIELDS })) {
      if (cover.exists) covers.set(cover.id, cover);
    }
  }

  return ranked.flatMap(({ id, doc }) => {
    const found = doc ?? covers.get(id);
    return found ? [toResult(found)] : [];
  });
}
