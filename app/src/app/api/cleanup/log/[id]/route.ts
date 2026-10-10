import { NextRequest, NextResponse } from "next/server";
import { CleanupRepository } from "@/lib/cleanup-repository";
import { db, originalsBucket } from "@/lib/gcp-clients";

export const dynamic = "force-dynamic";

/** One audit entry in full: what was marked deleted, item by item, and the evidence it was safe. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const entry = await new CleanupRepository(db(), originalsBucket()).logEntry(id);
    return entry ? NextResponse.json(entry) : NextResponse.json({ error: "Not found" }, { status: 404 });
  } catch (err) {
    console.error("[api/cleanup/log]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
