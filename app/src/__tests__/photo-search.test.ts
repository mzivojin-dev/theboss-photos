import { PHOTO_RESULT_FIELDS } from "@/lib/photo-index-repository";
import { searchPhotos } from "@/lib/photo-search";
import { localDayRange, parseSearchParams } from "@/lib/search-params";

const MODEL = "open_clip/ViT-B-16-SigLIP2/webli";
const query = (embedding: number[]) => ({ model: MODEL, embedding });

interface Fields {
  takenAt?: string;
  groupedUnder?: string;
  groupSize?: number;
}

const snap = (id: string, { takenAt = "2025-07-01T10:00:00Z", groupedUnder, groupSize }: Fields = {}) => ({
  id,
  exists: true,
  data: () => ({
    taken_at: { toDate: () => new Date(takenAt) },
    preview_gcs_path: `previews/${id}.webp`,
    original_gcs_path: `originals/${id}.jpg`,
    width: 1280,
    height: 960,
    grouped_under: groupedUnder,
    group_size: groupSize,
  }),
});

/** A Firestore stand-in whose vector query returns `neighbours` in order, and `getAll` the `covers`. */
function fakeDb(neighbours: ReturnType<typeof snap>[], covers: ReturnType<typeof snap>[] = []) {
  const findNearest = jest.fn().mockReturnValue({ get: async () => ({ docs: neighbours }) });
  const where = jest.fn(() => ({
    select: (...fields: string[]) => {
      expect(fields).toEqual(PHOTO_RESULT_FIELDS);
      return { findNearest };
    },
  }));
  const collection = { where, doc: (id: string) => ({ id }) };
  const getAll = jest.fn(async (...args: ({ id: string } | { fieldMask: string[] })[]) =>
    args.flatMap((ref) => ("id" in ref ? [covers.find((c) => c.id === ref.id) ?? { id: ref.id, exists: false }] : [])));
  return { db: { collection: () => collection, getAll } as any, findNearest, getAll, where };
}

describe("searchPhotos", () => {
  it("returns the nearest photos in rank order", async () => {
    const { db, findNearest } = fakeDb([snap("b"), snap("a"), snap("c")]);
    const photos = await searchPhotos(db, query([0.1, 0.2]), { limit: 2 });
    expect(photos.map((p) => p.id)).toEqual(["b", "a"]);
    expect(findNearest).toHaveBeenCalledWith(expect.objectContaining({
      vectorField: "embedding", queryVector: [0.1, 0.2], distanceMeasure: "COSINE", limit: 6,
    }));
  });

  it("compares the query only with photos embedded by the same model", async () => {
    const { db, where } = fakeDb([snap("a")]);
    await searchPhotos(db, query([1]), { limit: 10 });
    expect(where).toHaveBeenCalledWith("embedding_model", "==", MODEL);
  });

  it("shows a photo behind a cover as the cover, once, at the rank of its best match", async () => {
    const { db, getAll } = fakeDb(
      [snap("hidden1", { groupedUnder: "cover" }), snap("solo"), snap("cover", { groupSize: 3 }), snap("hidden2", { groupedUnder: "cover" })],
      [snap("cover", { groupSize: 3 })],
    );
    const photos = await searchPhotos(db, query([1]), { limit: 10 });
    expect(photos.map((p) => [p.id, p.groupSize])).toEqual([["cover", 3], ["solo", undefined]]);
    expect(getAll).toHaveBeenCalledWith({ id: "cover" }, { fieldMask: PHOTO_RESULT_FIELDS });
  });

  it("leaves out a cover that no longer exists", async () => {
    const { db } = fakeDb([snap("hidden", { groupedUnder: "gone" }), snap("solo")]);
    expect((await searchPhotos(db, query([1]), { limit: 10 })).map((p) => p.id)).toEqual(["solo"]);
  });

  it("keeps only photos taken in the date range, asking for as many neighbours as Firestore allows", async () => {
    const { db, findNearest } = fakeDb([
      snap("before", { takenAt: "2025-06-30T23:59:59Z" }),
      snap("first", { takenAt: "2025-07-01T00:00:00Z" }),
      snap("last", { takenAt: "2025-07-31T23:59:59Z" }),
      snap("after", { takenAt: "2025-08-01T00:00:00Z" }),
    ]);
    const photos = await searchPhotos(db, query([1]), {
      limit: 10, from: new Date("2025-07-01T00:00:00Z"), to: new Date("2025-08-01T00:00:00Z"),
    });
    expect(photos.map((p) => p.id)).toEqual(["first", "last"]);
    expect(findNearest).toHaveBeenCalledWith(expect.objectContaining({ limit: 1000 }));
  });

  it("does not read covers when nothing in the results is hidden", async () => {
    const { db, getAll } = fakeDb([snap("a")]);
    await searchPhotos(db, query([1]), { limit: 10 });
    expect(getAll).not.toHaveBeenCalled();
  });
});

describe("parseSearchParams", () => {
  const parse = (query: string) => parseSearchParams(new URLSearchParams(query));

  it("reads the query and the range as instants", () => {
    expect(parse("q=%20beach%20&from=2025-06-30T22:00:00.000Z&to=2025-07-31T22:00:00.000Z")).toEqual({
      q: "beach",
      from: new Date("2025-06-30T22:00:00Z"),
      to: new Date("2025-07-31T22:00:00Z"),
    });
    expect(parse("q=a&from=2025-07-01T00:00%2B02:00")).toEqual({ q: "a", from: new Date("2025-06-30T22:00:00Z"), to: undefined });
  });

  it("needs only q", () => {
    expect(parse("q=snow")).toEqual({ q: "snow", from: undefined, to: undefined });
  });

  it.each([
    ["", "q is required"],
    ["q=%20", "q is required"],
    [`q=${"x".repeat(501)}`, "q must be at most 500 characters"],
    ["q=a&from=2025-07-01", "from and to must be ISO 8601 instants with a zone"],
    ["q=a&to=2025-07-01T00:00:00", "from and to must be ISO 8601 instants with a zone"],
    ["q=a&to=2025-13-45T00:00Z", "from and to must be ISO 8601 instants with a zone"],
    ["q=a&from=2025-08-01T00:00Z&to=2025-08-01T00:00Z", "from must be before to"],
  ])("refuses %s", (query, error) => {
    expect(parse(query)).toEqual({ error });
  });
});

describe("localDayRange", () => {
  // Runs in the machine's own time zone, as the browser does; in a zone with daylight saving, the
  // days the clocks change are 23 and 25 hours long.
  const localMidnight = (iso: string) => {
    const date = new Date(iso);
    return [date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours(), date.getMinutes()];
  };

  it("bounds the picked days by local midnights, the last day included", () => {
    const { from, to } = localDayRange("2025-07-01", "2025-07-31");
    expect(localMidnight(from!)).toEqual([2025, 7, 1, 0, 0]);
    expect(localMidnight(to!)).toEqual([2025, 8, 1, 0, 0]);
  });

  it("ends every day of the year at the next local midnight, daylight-saving changes included", () => {
    for (let day = new Date(2025, 0, 1); day.getFullYear() === 2025; day.setDate(day.getDate() + 1)) {
      const iso = `2025-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
      const next = new Date(2025, day.getMonth(), day.getDate() + 1);
      expect(localMidnight(localDayRange(iso, iso).to!)).toEqual(
        [next.getFullYear(), next.getMonth() + 1, next.getDate(), 0, 0]);
    }
  });

  it("leaves out a day that wasn't picked", () => {
    expect(localDayRange("", "2025-07-31").from).toBeUndefined();
    expect(localDayRange("2025-07-01", "").to).toBeUndefined();
  });
});
