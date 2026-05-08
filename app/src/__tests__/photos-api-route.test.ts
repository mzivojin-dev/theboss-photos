/**
 * Tests for /api/photos route — verifies youtubeVideoId is passed through.
 */
import { GET } from "@/app/api/photos/route";

jest.mock("@/lib/gcp-clients", () => ({
  db: jest.fn(() => ({})),
  previewsBucket: jest.fn(() => ({})),
}));

jest.mock("@/lib/gcs", () => ({
  generateSignedPreviewUrl: jest.fn().mockResolvedValue("https://signed.url/preview.webp"),
}));

jest.mock("@/lib/photo-index-repository");

const { PhotoIndexRepository } = jest.requireMock("@/lib/photo-index-repository");

function makeRequest(params: Record<string, string> = {}): any {
  const searchParams = new URLSearchParams(params);
  return { nextUrl: { searchParams } };
}

describe("GET /api/photos", () => {
  beforeEach(() => jest.clearAllMocks());

  it("includes youtubeVideoId in response for video documents", async () => {
    PhotoIndexRepository.prototype.list = jest.fn().mockResolvedValue({
      photos: [
        {
          id: "VID1",
          takenAt: new Date("2023-07-15"),
          previewGcsPath: null,
          originalGcsPath: null,
          youtubeVideoId: "yt-abc-123",
          width: null,
          height: null,
        },
      ],
      nextCursor: null,
    });

    const res = await GET(makeRequest());
    const body = await res.json();

    expect(body.photos[0].youtubeVideoId).toBe("yt-abc-123");
  });

  it("omits youtubeVideoId for image documents", async () => {
    PhotoIndexRepository.prototype.list = jest.fn().mockResolvedValue({
      photos: [
        {
          id: "IMG1",
          takenAt: new Date("2023-07-15"),
          previewGcsPath: "previews/IMG1.webp",
          originalGcsPath: "originals/IMG1.jpg",
          youtubeVideoId: undefined,
          width: 1280,
          height: 960,
        },
      ],
      nextCursor: null,
    });

    const res = await GET(makeRequest());
    const body = await res.json();

    expect(body.photos[0].youtubeVideoId).toBeUndefined();
  });
});
