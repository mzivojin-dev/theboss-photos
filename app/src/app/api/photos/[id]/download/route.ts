import { NextRequest, NextResponse } from "next/server";
import { db, originalsBucket } from "@/lib/gcp-clients";
import { generateSignedDownloadUrl } from "@/lib/gcs";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const doc = await db.collection("photos").doc(id).get();

  if (!doc.exists) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const originalGcsPath: string = doc.data()!.originalGcsPath;
  const url = await generateSignedDownloadUrl(originalGcsPath, originalsBucket);

  return NextResponse.redirect(url, 302);
}
