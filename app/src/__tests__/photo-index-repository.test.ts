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
  });
});
