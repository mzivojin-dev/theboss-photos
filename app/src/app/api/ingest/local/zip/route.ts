import { NextRequest, NextResponse } from "next/server";
import { createWriteStream } from "fs";
import { unlink } from "fs/promises";
import { join } from "path";
import { tmpdir } from "os";
import { Readable } from "stream";
import { pipeline } from "stream/promises";
import { emitIngestEvent } from "@/lib/local-ingest-events";
import { runPythonIngest } from "@/lib/local-ingest-runner";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "https://takeout.google.com",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Takeout-Index, X-Takeout-Total",
};

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}

export async function POST(req: NextRequest) {
  const rawIndex = req.headers.get("x-takeout-index") ?? "0";
  const rawTotal = req.headers.get("x-takeout-total") ?? "?";
  const label = `[${Number(rawIndex) + 1}/${rawTotal}]`;

  if (!req.body) {
    return NextResponse.json({ error: "empty body" }, { status: 400, headers: CORS_HEADERS });
  }

  const tmpPath = join(tmpdir(), `takeout-${Date.now()}-${rawIndex}.zip`);
  emitIngestEvent({ type: "start", message: `${label} Receiving ZIP...` });

  try {
    await pipeline(
      Readable.fromWeb(req.body as Parameters<typeof Readable.fromWeb>[0]),
      createWriteStream(tmpPath),
    );
    emitIngestEvent({ type: "log", message: `${label} Saved to disk, running ingestion...` });

    await runPythonIngest(tmpPath, label);
    emitIngestEvent({ type: "done", message: `${label} Done.` });
    return NextResponse.json({ ok: true }, { headers: CORS_HEADERS });
  } catch (err) {
    emitIngestEvent({ type: "error", message: `${label} Error: ${String(err)}` });
    return NextResponse.json({ error: String(err) }, { status: 500, headers: CORS_HEADERS });
  } finally {
    await unlink(tmpPath).catch(() => {});
  }
}

