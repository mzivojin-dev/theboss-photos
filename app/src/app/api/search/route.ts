import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/gcp-clients";
import { embedText } from "@/lib/embed-client";
import { searchPhotos } from "@/lib/photo-search";
import { toPhotoDto } from "@/lib/photo-dto";
import { parseSearchParams } from "@/lib/search-params";

/**
 * Semantic search: `GET /api/search?q=kids+on+a+beach[&from=YYYY-MM-DD][&to=YYYY-MM-DD]`, both days
 * inclusive (UTC). Returns up to 60 photos, best match first.
 */
export async function GET(req: NextRequest) {
  const params = parseSearchParams(req.nextUrl.searchParams);
  if ("error" in params) return NextResponse.json({ error: params.error }, { status: 400 });
  try {
    const { embedding } = await embedText(params.q);
    const photos = await searchPhotos(db(), embedding, { limit: 60, from: params.from, to: params.to });
    return NextResponse.json({ photos: await Promise.all(photos.map(toPhotoDto)) });
  } catch (err) {
    console.error("[api/search]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
