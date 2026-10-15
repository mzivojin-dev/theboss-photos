import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/gcp-clients";
import { embedText } from "@/lib/embed-client";
import { searchPhotos } from "@/lib/photo-search";
import { toPhotoDto } from "@/lib/photo-dto";
import { parseSearchParams } from "@/lib/search-params";

/**
 * Semantic search: `GET /api/search?q=kids+on+a+beach[&from=<instant>][&to=<instant>]`, photos taken
 * in [from, to) (ISO 8601 with a zone; the search box sends the user's local midnights). Returns up
 * to 60 photos, best match first.
 */
export async function GET(req: NextRequest) {
  const params = parseSearchParams(req.nextUrl.searchParams);
  if ("error" in params) return NextResponse.json({ error: params.error }, { status: 400 });
  try {
    const photos = await searchPhotos(db(), await embedText(params.q), { limit: 60, from: params.from, to: params.to });
    return NextResponse.json({ photos: await Promise.all(photos.map(toPhotoDto)) });
  } catch (err) {
    console.error("[api/search]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
