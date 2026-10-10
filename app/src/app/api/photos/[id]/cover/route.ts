import { NextRequest, NextResponse } from "next/server";
import { pinCover } from "@/lib/photo-index-repository";
import { toPhotoDto } from "@/lib/photo-dto";
import { db } from "@/lib/gcp-clients";

/** Makes this photo the cover of its group; the grouping job keeps the choice. */
export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const cover = await pinCover(db(), id);
    if (!cover) return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json({ photo: await toPhotoDto(cover) });
  } catch (err) {
    console.error("[api/photos/cover]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
