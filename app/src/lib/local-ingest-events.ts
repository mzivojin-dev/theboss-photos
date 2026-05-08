import { EventEmitter } from "events";

export type IngestEvent = {
  type: "start" | "log" | "done" | "error" | "links";
  message: string;
  urls?: string[];
  cookies?: string;
};

const emitter = new EventEmitter();
emitter.setMaxListeners(20);

export function emitIngestEvent(event: IngestEvent): void {
  emitter.emit("ingest", event);
}

export function onIngestEvent(handler: (event: IngestEvent) => void): () => void {
  emitter.on("ingest", handler);
  return () => emitter.off("ingest", handler);
}
