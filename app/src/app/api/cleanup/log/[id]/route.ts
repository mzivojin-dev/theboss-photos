import { NextRequest, NextResponse } from "next/server";
import { cleanupStore } from "@/lib/cleanup-store";

export const dynamic = "force-dynamic";

/** One audit entry in full: what was marked deleted, item by item, and the evidence it was safe. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const entry = await cleanupStore().logEntry(id);
    return entry ? NextResponse.json(entry) : NextResponse.json({ error: "Not found" }, { status: 404 });
  } catch (err) {
    console.error("[api/cleanup/log]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
