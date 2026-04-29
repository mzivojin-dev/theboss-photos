/**
 * RED: tests for GCS signed URL generation
 * Fail until src/lib/gcs.ts is implemented.
 */
import { generateSignedPreviewUrl, generateSignedDownloadUrl } from "@/lib/gcs";

describe("generateSignedPreviewUrl", () => {
  it("returns a string URL", async () => {
    const mockBucket = {
      file: jest.fn().mockReturnValue({
        getSignedUrl: jest.fn().mockResolvedValue(["https://storage.googleapis.com/fake-url"]),
      }),
    };
    const url = await generateSignedPreviewUrl("previews/AAA.webp", mockBucket as any);
    expect(typeof url).toBe("string");
    expect(url).toContain("https://");
  });

  it("requests GET action with 1 hour expiry", async () => {
    const getSignedUrl = jest.fn().mockResolvedValue(["https://storage.googleapis.com/fake-url"]);
    const mockBucket = { file: jest.fn().mockReturnValue({ getSignedUrl }) };

    await generateSignedPreviewUrl("previews/AAA.webp", mockBucket as any);

    const [opts] = getSignedUrl.mock.calls[0];
    expect(opts.action).toBe("read");
    expect(opts.expires).toBeDefined();
  });
});

describe("generateSignedDownloadUrl", () => {
  it("returns a string URL", async () => {
    const mockBucket = {
      file: jest.fn().mockReturnValue({
        getSignedUrl: jest.fn().mockResolvedValue(["https://storage.googleapis.com/fake-download-url"]),
      }),
    };
    const url = await generateSignedDownloadUrl("originals/AAA_IMG_0001.jpg", mockBucket as any);
    expect(typeof url).toBe("string");
  });

  it("requests GET action", async () => {
    const getSignedUrl = jest.fn().mockResolvedValue(["https://storage.googleapis.com/fake-url"]);
    const mockBucket = { file: jest.fn().mockReturnValue({ getSignedUrl }) };

    await generateSignedDownloadUrl("originals/AAA.jpg", mockBucket as any);

    const [opts] = getSignedUrl.mock.calls[0];
    expect(opts.action).toBe("read");
  });
});
