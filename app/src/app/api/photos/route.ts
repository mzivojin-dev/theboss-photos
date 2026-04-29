import { NextRequest, NextResponse } from "next/server";
import { PhotoIndexRepository } from "@/lib/photo-index-repository";
import { generateSignedPreviewUrl } from "@/lib/gcs";
import { db, previewsBucket } from "@/lib/gcp-clients";

const repo = new PhotoIndexRepository(db);

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const cursor = searchParams.get("cursor") ?? undefined;
  const limit = 50;

  const { photos, nextCursor } = await repo.list({ limit, cursor });

  const photosWithUrls = await Promise.all(
    photos.map(async (photo) => ({
      id: photo.id,
      takenAt: photo.takenAt.toISOString(),
      previewUrl: await generateSignedPreviewUrl(photo.previewGcsPath, previewsBucket),
      width: photo.width,
      height: photo.height,
    }))
  );

  return NextResponse.json({ photos: photosWithUrls, nextCursor });
}
