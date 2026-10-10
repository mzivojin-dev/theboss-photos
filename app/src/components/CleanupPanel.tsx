"use client";

import { useCallback, useEffect, useState } from "react";

interface SafeRange { start: string; end: string; itemCount: number }
interface UnsafeDay { day: string; itemCount: number; reasons: string[] }
interface Problem { kind: string; path: string; reason: string }
interface Report {
  safeRanges: SafeRange[];
  unsafeDays: UnsafeDay[];
  undatedProblems: Problem[];
  deletedDays: string[];
}

const REASON_LABELS: Record<string, string> = {
  not_covered: "year not in any Takeout export",
  after_export: "taken on or after the export date",
  problem_nearby: "a file within a day failed to index",
  original_missing: "an Original is missing from the bucket",
};

const PROBLEM_LABELS: Record<string, string> = {
  failed: "failed to index",
  no_sidecar: "no Sidecar",
  bad_sidecar: "unreadable Sidecar",
};

const section = { margin: "1.5rem 0" } as const;
const muted = { color: "#999", fontSize: "0.85rem" } as const;

export default function CleanupPanel() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/cleanup", { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to load the cleanup list");
      setReport(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const markDeleted = async (range: SafeRange) => {
    setBusy(range.start);
    try {
      const res = await fetch("/api/cleanup/deleted", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: range.start, end: range.end }),
      });
      if (!res.ok) throw new Error((await res.json()).error ?? "Failed to save");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ padding: "1rem 1.5rem", maxWidth: 860 }}>
      <p style={muted}>
        Google Photos has no delete API, so delete these days by hand: open the day in photos.google.com, tick its
        date header, and delete. Then press the button so the range drops off this list. Deleted items stay in
        Photos Trash for 60 days; storage is only freed once Trash is emptied (after 60 days, or by hand).
      </p>
      <p style={muted}>
        Residual risk: a photo taken before the export date but added to Google Photos after it (a scan, or a photo
        sent to you with an old date) is in no archive. Check each day in Photos before deleting it.
      </p>

      {error && <p style={{ color: "#f44336" }}>{error}</p>}
      {!report && !error && <p style={muted}>Loading…</p>}

      {report && (
        <>
          <section style={section}>
            <h2 style={{ fontSize: "1rem" }}>Safe to delete ({report.safeRanges.length} ranges)</h2>
            {report.safeRanges.length === 0 && <p style={muted}>Nothing is safe to delete yet.</p>}
            {report.safeRanges.map((range) => (
              <div key={range.start} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid #333" }}>
                <span>
                  {range.start === range.end ? range.start : `${range.start} → ${range.end}`}
                  <span style={muted}> · {range.itemCount} item{range.itemCount === 1 ? "" : "s"}</span>
                </span>
                <button onClick={() => markDeleted(range)} disabled={busy !== null}>
                  {busy === range.start ? "Saving…" : "Deleted in Google Photos"}
                </button>
              </div>
            ))}
          </section>

          <details style={section}>
            <summary>Not safe ({report.unsafeDays.length} days with media)</summary>
            {report.unsafeDays.map((day) => (
              <div key={day.day} style={{ padding: "0.25rem 0" }}>
                {day.day} <span style={muted}>· {day.itemCount} · {day.reasons.map((r) => REASON_LABELS[r] ?? r).join("; ")}</span>
              </div>
            ))}
          </details>

          <details style={section}>
            <summary>Files to resolve ({report.undatedProblems.length})</summary>
            <p style={muted}>No date is known for these, so they can’t block a particular day. See the ingestion job logs.</p>
            {report.undatedProblems.map((problem) => (
              <div key={problem.path} style={{ padding: "0.25rem 0" }}>
                {problem.path} <span style={muted}>· {PROBLEM_LABELS[problem.kind] ?? problem.kind}</span>
              </div>
            ))}
          </details>

          <p style={muted}>{report.deletedDays.length} days already marked deleted.</p>
        </>
      )}
    </div>
  );
}
