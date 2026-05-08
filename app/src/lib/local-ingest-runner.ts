import { spawn } from "child_process";
import { join } from "path";
import { emitIngestEvent } from "@/lib/local-ingest-events";

export function runPythonIngest(zipPath: string, label: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const python = process.env.PYTHON_EXECUTABLE ?? "python";
    const cwd = join(process.cwd(), "..", "jobs", "ingest");
    const proc = spawn(python, ["-m", "src.local_main", "--zip-path", zipPath], {
      cwd,
      env: process.env as NodeJS.ProcessEnv,
    });

    const onLine = (line: string) =>
      emitIngestEvent({ type: "log", message: `${label} ${line}` });

    proc.stdout.on("data", (d: Buffer) =>
      d.toString().split("\n").filter(Boolean).forEach(onLine),
    );
    proc.stderr.on("data", (d: Buffer) =>
      d.toString().split("\n").filter(Boolean).forEach(onLine),
    );
    proc.on("close", (code) =>
      code === 0 ? resolve() : reject(new Error(`python exited ${code}`)),
    );
  });
}
