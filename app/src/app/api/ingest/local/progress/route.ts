import { NextResponse } from "next/server";
import { onIngestEvent, IngestEvent } from "@/lib/local-ingest-events";

export async function GET() {
  const encoder = new TextEncoder();
  let cleanup: (() => void) | null = null;
  let heartbeat: ReturnType<typeof setInterval> | null = null;

  const stream = new ReadableStream({
    start(controller) {
      cleanup = onIngestEvent((event: IngestEvent) => {
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        } catch {
          /* controller closed */
        }
      });

      heartbeat = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(": ping\n\n"));
        } catch {
          /* controller closed */
        }
      }, 30_000);
    },
    cancel() {
      cleanup?.();
      if (heartbeat) clearInterval(heartbeat);
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
