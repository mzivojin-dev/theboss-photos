import { PHOTO_RESULT_FIELDS } from "@/lib/photo-index-repository";
import { searchPhotos } from "@/lib/photo-search";
import { parseSearchParams } from "@/lib/search-params";

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
  const collection = {
    select: jest.fn((...fields: string[]) => {
      expect(fields).toEqual(PHOTO_RESULT_FIELDS);
      return { findNearest };
    }),
    doc: (id: string) => ({ id }),
  };
  const getAll = jest.fn(async (...args: ({ id: string } | { fieldMask: string[] })[]) =>
    args.flatMap((ref) => ("id" in ref ? [covers.find((c) => c.id === ref.id) ?? { id: ref.id, exists: false }] : [])));
  return { db: { collection: () => collection, getAll } as any, findNearest, getAll };
}

describe("searchPhotos", () => {
  it("returns the nearest photos in rank order", async () => {
    const { db, findNearest } = fakeDb([snap("b"), snap("a"), snap("c")]);
    const photos = await searchPhotos(db, [0.1, 0.2], { limit: 2 });
    expect(photos.map((p) => p.id)).toEqual(["b", "a"]);
    expect(findNearest).toHaveBeenCalledWith(expect.objectContaining({
      vectorField: "embedding", queryVector: [0.1, 0.2], distanceMeasure: "COSINE", limit: 6,
    }));
  });

  it("shows a photo behind a cover as the cover, once, at the rank of its best match", async () => {
    const { db, getAll } = fakeDb(
      [snap("hidden1", { groupedUnder: "cover" }), snap("solo"), snap("cover", { groupSize: 3 }), snap("hidden2", { groupedUnder: "cover" })],
      [snap("cover", { groupSize: 3 })],
    );
    const photos = await searchPhotos(db, [1], { limit: 10 });
    expect(photos.map((p) => [p.id, p.groupSize])).toEqual([["cover", 3], ["solo", undefined]]);
    expect(getAll).toHaveBeenCalledWith({ id: "cover" }, { fieldMask: PHOTO_RESULT_FIELDS });
  });

  it("leaves out a cover that no longer exists", async () => {
    const { db } = fakeDb([snap("hidden", { groupedUnder: "gone" }), snap("solo")]);
    expect((await searchPhotos(db, [1], { limit: 10 })).map((p) => p.id)).toEqual(["solo"]);
  });

  it("keeps only photos taken in the date range, asking for as many neighbours as Firestore allows", async () => {
    const { db, findNearest } = fakeDb([
      snap("before", { takenAt: "2025-06-30T23:59:59Z" }),
      snap("first", { takenAt: "2025-07-01T00:00:00Z" }),
      snap("last", { takenAt: "2025-07-31T23:59:59Z" }),
      snap("after", { takenAt: "2025-08-01T00:00:00Z" }),
    ]);
    const photos = await searchPhotos(db, [1], {
      limit: 10, from: new Date("2025-07-01T00:00:00Z"), to: new Date("2025-08-01T00:00:00Z"),
    });
    expect(photos.map((p) => p.id)).toEqual(["first", "last"]);
    expect(findNearest).toHaveBeenCalledWith(expect.objectContaining({ limit: 1000 }));
  });

  it("does not read covers when nothing in the results is hidden", async () => {
    const { db, getAll } = fakeDb([snap("a")]);
    await searchPhotos(db, [1], { limit: 10 });
    expect(getAll).not.toHaveBeenCalled();
  });
});

describe("parseSearchParams", () => {
  const parse = (query: string) => parseSearchParams(new URLSearchParams(query));

  it("reads the query and makes the to-day inclusive", () => {
    expect(parse("q=%20beach%20&from=2025-07-01&to=2025-07-31")).toEqual({
      q: "beach",
      from: new Date("2025-07-01T00:00:00Z"),
      to: new Date("2025-08-01T00:00:00Z"),
    });
  });

  it("needs only q", () => {
    expect(parse("q=snow")).toEqual({ q: "snow", from: undefined, to: undefined });
  });

  it.each([
    ["", "q is required"],
    ["q=%20", "q is required"],
    [`q=${"x".repeat(501)}`, "q must be at most 500 characters"],
    ["q=a&from=2025-7-1", "from and to must be days, YYYY-MM-DD"],
    ["q=a&to=2025-13-45", "from and to must be days, YYYY-MM-DD"],
    ["q=a&from=2025-08-01&to=2025-07-01", "from must not be after to"],
  ])("refuses %s", (query, error) => {
    expect(parse(query)).toEqual({ error });
  });
});
