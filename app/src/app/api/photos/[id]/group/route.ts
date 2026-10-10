import { NextRequest, NextResponse } from "next/server";
import { PhotoIndexRepository } from "@/lib/photo-index-repository";
import { toPhotoDto } from "@/lib/photo-dto";
import { db } from "@/lib/gcp-clients";

/** The photos a cover stands for (the cover first), for the lightbox to step through. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const photos = await new PhotoIndexRepository(db()).group(id);
    return NextResponse.json({ photos: await Promise.all(photos.map(toPhotoDto)) });
  } catch (err) {
    console.error("[api/photos/group]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
