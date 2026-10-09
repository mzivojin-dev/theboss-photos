/**
 * RED: tests for PhotoIndexRepository
 * Fail until src/lib/photo-index-repository.ts is implemented.
 */
import { PhotoIndexRepository, PhotoDoc } from "@/lib/photo-index-repository";

const makeDoc = (overrides: Partial<PhotoDoc> = {}): PhotoDoc => ({
  googlePhotosId: "AAA123",
  filename: "IMG_0001.jpg",
  takenAt: new Date("2021-01-01T00:00:00Z"),
  previewGcsPath: "previews/AAA123.webp",
  originalGcsPath: "originals/AAA123_IMG_0001.jpg",
  width: 1280,
  height: 960,
  latitude: null,
  longitude: null,
  ...overrides,
});

describe("PhotoIndexRepository", () => {
  let mockDb: any;
  let repo: PhotoIndexRepository;

  beforeEach(() => {
    mockDb = {
      collection: jest.fn().mockReturnThis(),
      where: jest.fn().mockReturnThis(),
      orderBy: jest.fn().mockReturnThis(),
      limit: jest.fn().mockReturnThis(),
      startAfter: jest.fn().mockReturnThis(),
      get: jest.fn(),
      doc: jest.fn().mockReturnThis(),
      set: jest.fn(),
    };
    mockDb.collection.mockReturnValue(mockDb);
    mockDb.where.mockReturnValue(mockDb);
    mockDb.orderBy.mockReturnValue(mockDb);
    mockDb.limit.mockReturnValue(mockDb);
    mockDb.startAfter.mockReturnValue(mockDb);
    mockDb.doc.mockReturnValue({ get: jest.fn().mockResolvedValue({ exists: false }) });
    repo = new PhotoIndexRepository(mockDb);
  });

  describe("list", () => {
    it("returns photos in order from Firestore", async () => {
      const fakeDocs = [
        { id: "AAA", data: () => ({ ...makeDoc(), taken_at: { toDate: () => new Date("2021-06-01") } }) },
        { id: "BBB", data: () => ({ ...makeDoc({ googlePhotosId: "BBB" }), taken_at: { toDate: () => new Date("2021-01-01") } }) },
      ];
      mockDb.get.mockResolvedValue({ docs: fakeDocs });

      const result = await repo.list({ limit: 50 });
      expect(result.photos).toHaveLength(2);
    });

    it("returns nextCursor when more results exist", async () => {
      const fakeDocs = Array.from({ length: 50 }, (_, i) => ({
        id: `ID${i}`,
        data: () => ({ ...makeDoc(), taken_at: { toDate: () => new Date() } }),
      }));
      mockDb.get.mockResolvedValue({ docs: fakeDocs });

      const result = await repo.list({ limit: 50 });
      expect(result.nextCursor).toBe("ID49");
    });

    it("returns null nextCursor when fewer results than limit", async () => {
      const fakeDocs = [
        { id: "AAA", data: () => ({ ...makeDoc(), taken_at: { toDate: () => new Date() } }) },
      ];
      mockDb.get.mockResolvedValue({ docs: fakeDocs });

      const result = await repo.list({ limit: 50 });
      expect(result.nextCursor).toBeNull();
    });

    it("leaves out photos grouped behind a cover and keeps going until the page is full", async () => {
      const doc = (id: string, extra = {}) => ({
        id,
        data: () => ({ ...makeDoc(), taken_at: { toDate: () => new Date() }, ...extra }),
      });
      mockDb.get
        .mockResolvedValueOnce({ docs: [doc("A", { group_size: 3 }), doc("B", { grouped_under: "A" })] })
        .mockResolvedValueOnce({ docs: [] });

      const result = await repo.list({ limit: 2 });
      expect(result.photos.map((p) => p.id)).toEqual(["A"]);
      expect(result.photos[0].groupSize).toBe(3);
      expect(result.nextCursor).toBeNull();
    });

    it("continues from the last photo looked at, even when it was hidden", async () => {
      const doc = (id: string, extra = {}) => ({
        id,
        data: () => ({ ...makeDoc(), taken_at: { toDate: () => new Date() }, ...extra }),
      });
      mockDb.get
        .mockResolvedValueOnce({ docs: [doc("A"), doc("B", { grouped_under: "A" })] })
        .mockResolvedValueOnce({ docs: [doc("C"), doc("D", { grouped_under: "C" })] });

      const result = await repo.list({ limit: 2 });
      expect(result.photos.map((p) => p.id)).toEqual(["A", "C"]);
      expect(result.nextCursor).toBe("D");
    });
  });

  describe("group", () => {
    it("returns the cover first, then the photos behind it in the order they were taken", async () => {
      const doc = (id: string, day: number) => ({
        id,
        exists: true,
        data: () => ({ ...makeDoc(), taken_at: { toDate: () => new Date(2021, 0, day) } }),
      });
      mockDb.doc.mockReturnValue({ get: jest.fn().mockResolvedValue(doc("COVER", 5)) });
      mockDb.get.mockResolvedValue({ docs: [doc("LATE", 7), doc("EARLY", 4)] });

      const photos = await repo.group("COVER");
      expect(photos.map((p) => p.id)).toEqual(["COVER", "EARLY", "LATE"]);
    });
  });
});
