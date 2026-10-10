import type { Photo } from "./photo";
import type { PhotoResult } from "./photo-index-repository";
import { generateSignedPreviewUrl } from "./gcs";
import { previewsBucket } from "./gcp-clients";

/** A photo from the Photo Index as the browser gets it, with a signed URL for its preview. */
export async function toPhotoDto(photo: PhotoResult): Promise<Photo> {
  return {
    id: photo.id,
    takenAt: photo.takenAt.toISOString(),
    previewUrl: photo.previewGcsPath
      ? await generateSignedPreviewUrl(photo.previewGcsPath, previewsBucket())
      : null,
    width: photo.width,
    height: photo.height,
    groupSize: photo.groupSize ?? null,
  };
}
