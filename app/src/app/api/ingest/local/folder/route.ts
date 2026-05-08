import { NextRequest, NextResponse } from "next/server";
import { readdirSync } from "fs";
import { join } from "path";
import { emitIngestEvent } from "@/lib/local-ingest-events";
import { runPythonIngest } from "@/lib/local-ingest-runner";

export async function POST(req: NextRequest) {
  const { folder } = await req.json() as { folder: string };

  let zips: string[];
  try {
    zips = readdirSync(folder)
      .filter((f) => f.toLowerCase().endsWith(".zip"))
      .sort()
      .map((f) => join(folder, f));
  } catch (err) {
    return NextResponse.json({ error: `Cannot read folder: ${err}` }, { status: 400 });
  }

  if (zips.length === 0) {
    return NextResponse.json({ error: "No ZIP files found in that folder." }, { status: 400 });
  }

  emitIngestEvent({ type: "start", message: `Found ${zips.length} ZIP(s) in ${folder}` });

  // Run in background — caller gets immediate response, progress arrives via SSE
  (async () => {
    for (let i = 0; i < zips.length; i++) {
      const label = `[${i + 1}/${zips.length}]`;
      const name = zips[i].replace(/\\/g, "/").split("/").pop() ?? zips[i];
      emitIngestEvent({ type: "start", message: `${label} Processing ${name}...` });
      try {
        await runPythonIngest(zips[i], label);
        emitIngestEvent({ type: "done", message: `${label} Done.` });
      } catch (err) {
        emitIngestEvent({ type: "error", message: `${label} Error: ${String(err)}` });
      }
    }
    emitIngestEvent({ type: "done", message: "All ZIPs processed." });
  })();

  return NextResponse.json({ started: true, count: zips.length });
}
