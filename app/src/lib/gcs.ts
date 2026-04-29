import type { Bucket } from "@google-cloud/storage";

const ONE_HOUR_MS = 60 * 60 * 1000;

export async function generateSignedPreviewUrl(
  gcsPath: string,
  bucket: Bucket
): Promise<string> {
  const [url] = await bucket.file(gcsPath).getSignedUrl({
    action: "read",
    expires: Date.now() + ONE_HOUR_MS,
  });
  return url;
}

export async function generateSignedDownloadUrl(
  gcsPath: string,
  bucket: Bucket
): Promise<string> {
  const [url] = await bucket.file(gcsPath).getSignedUrl({
    action: "read",
    expires: Date.now() + ONE_HOUR_MS,
    responseDisposition: `attachment; filename="${gcsPath.split("/").pop()}"`,
  });
  return url;
}
