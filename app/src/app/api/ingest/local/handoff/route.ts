import { NextRequest, NextResponse } from "next/server";
import { emitIngestEvent } from "@/lib/local-ingest-events";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://takeout.google.com",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}

export async function POST(req: NextRequest) {
  const { urls, cookies } = (await req.json()) as { urls: string[]; cookies: string };

  if (!Array.isArray(urls) || urls.length === 0) {
    return NextResponse.json({ error: "No URLs provided." }, { status: 400, headers: CORS_HEADERS });
  }

  emitIngestEvent({ type: "links", message: `Received ${urls.length} download link(s)`, urls, cookies });
  return NextResponse.json({ ok: true, count: urls.length }, { headers: CORS_HEADERS });
}
