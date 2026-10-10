import { NextRequest, NextResponse } from "next/server";
import { CleanupRepository, isValidDay, MAX_RANGE_DAYS } from "@/lib/cleanup-repository";
import { db, originalsBucket } from "@/lib/gcp-clients";

/** Records that a range of days was deleted in Google Photos, so it drops off the safe list. */
export async function POST(req: NextRequest) {
  try {
    const { start, end } = await req.json();
    if (!isValidDay(start) || !isValidDay(end) || start > end) {
      return NextResponse.json({ error: "start and end must be YYYY-MM-DD dates, start first" }, { status: 400 });
    }
    if ((Date.parse(end) - Date.parse(start)) / 86_400_000 >= MAX_RANGE_DAYS) {
      return NextResponse.json({ error: "Range is too long" }, { status: 400 });
    }
    const days = await new CleanupRepository(db(), originalsBucket()).markDeleted(start, end);
    return NextResponse.json({ days });
  } catch (err) {
    console.error("[api/cleanup/deleted]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
