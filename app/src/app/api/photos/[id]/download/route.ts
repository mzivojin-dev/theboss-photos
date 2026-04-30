import { NextRequest, NextResponse } from "next/server";
import { db, originalsBucket } from "@/lib/gcp-clients";
import { generateSignedDownloadUrl } from "@/lib/gcs";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const doc = await db().collection("photos").doc(id).get();

    if (!doc.exists) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const originalGcsPath: string = doc.data()!.original_gcs_path;
    const url = await generateSignedDownloadUrl(originalGcsPath, originalsBucket());

    return NextResponse.redirect(url, 302);
  } catch (err) {
    console.error("[api/photos/download]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
