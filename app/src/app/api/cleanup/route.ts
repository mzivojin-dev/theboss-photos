import { NextResponse } from "next/server";
import { CleanupRepository } from "@/lib/cleanup-repository";
import { db, originalsBucket } from "@/lib/gcp-clients";

export const dynamic = "force-dynamic";

/** Safe-to-delete day ranges for Google Photos, the unsafe days with reasons, and undated problems. */
export async function GET() {
  try {
    const report = await new CleanupRepository(db(), originalsBucket()).report();
    return NextResponse.json({
      ...report,
      undatedProblems: report.undatedProblems.map(({ kind, path, reason }) => ({ kind, path, reason })),
    });
  } catch (err) {
    console.error("[api/cleanup]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
