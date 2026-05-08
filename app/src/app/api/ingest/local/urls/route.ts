import { NextRequest, NextResponse } from "next/server";
import { createWriteStream } from "fs";
import { unlink } from "fs/promises";
import { join } from "path";
import { tmpdir } from "os";
import { Readable } from "stream";
import { pipeline } from "stream/promises";
import { emitIngestEvent } from "@/lib/local-ingest-events";
import { runPythonIngest } from "@/lib/local-ingest-runner";

export async function POST(req: NextRequest) {
  const { urls, cookies } = (await req.json()) as { urls: string[]; cookies: string };

  if (!Array.isArray(urls) || urls.length === 0) {
    return NextResponse.json({ error: "No URLs provided." }, { status: 400 });
  }

  emitIngestEvent({ type: "start", message: `Processing ${urls.length} URL(s)…` });

  (async () => {
    for (let i = 0; i < urls.length; i++) {
      const label = `[${i + 1}/${urls.length}]`;
      const tmpPath = join(tmpdir(), `takeout-url-${Date.now()}-${i}.zip`);
      emitIngestEvent({ type: "start", message: `${label} Downloading…` });
      try {
        const resp = await fetch(urls[i], {
          headers: cookies ? { Cookie: cookies } : {},
          redirect: "follow",
        });
        if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
        await pipeline(
          Readable.fromWeb(resp.body as Parameters<typeof Readable.fromWeb>[0]),
          createWriteStream(tmpPath),
        );
        emitIngestEvent({ type: "log", message: `${label} Downloaded, running ingestion…` });
        await runPythonIngest(tmpPath, label);
        emitIngestEvent({ type: "done", message: `${label} Done.` });
      } catch (err) {
        emitIngestEvent({ type: "error", message: `${label} Error: ${String(err)}` });
      } finally {
        await unlink(tmpPath).catch(() => {});
      }
    }
    emitIngestEvent({ type: "done", message: "All ZIPs processed." });
  })();

  return NextResponse.json({ started: true, count: urls.length });
}
