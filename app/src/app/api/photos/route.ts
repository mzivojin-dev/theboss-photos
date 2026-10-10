import { NextRequest, NextResponse } from "next/server";
import { PhotoIndexRepository } from "@/lib/photo-index-repository";
import { toPhotoDto } from "@/lib/photo-dto";
import { db } from "@/lib/gcp-clients";

export async function GET(req: NextRequest) {
  try {
    const repo = new PhotoIndexRepository(db());
    const { searchParams } = req.nextUrl;
    const cursor = searchParams.get("cursor") ?? undefined;
    const limit = 50;

    const { photos, nextCursor } = await repo.list({ limit, cursor });

    return NextResponse.json({ photos: await Promise.all(photos.map(toPhotoDto)), nextCursor });
  } catch (err) {
    console.error("[api/photos]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
