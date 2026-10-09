import { NextRequest, NextResponse } from "next/server";
import { PhotoIndexRepository } from "@/lib/photo-index-repository";
import { generateSignedPreviewUrl } from "@/lib/gcs";
import { db, previewsBucket } from "@/lib/gcp-clients";

/** The photos a cover stands for (the cover first), for the lightbox to step through. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const photos = await new PhotoIndexRepository(db()).group(id);
    const withUrls = await Promise.all(
      photos.map(async (photo) => ({
        id: photo.id,
        takenAt: photo.takenAt.toISOString(),
        previewUrl: photo.previewGcsPath
          ? await generateSignedPreviewUrl(photo.previewGcsPath, previewsBucket())
          : null,
        width: photo.width,
        height: photo.height,
      }))
    );
    return NextResponse.json({ photos: withUrls });
  } catch (err) {
    console.error("[api/photos/group]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
