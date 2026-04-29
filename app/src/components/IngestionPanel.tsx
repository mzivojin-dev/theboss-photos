"use client";

import { useState, useEffect, useRef } from "react";

type Status = "IDLE" | "RUNNING" | "SUCCEEDED" | "FAILED";

const STATUS_COLORS: Record<Status, string> = {
  IDLE: "#666",
  RUNNING: "#f0a500",
  SUCCEEDED: "#4caf50",
  FAILED: "#f44336",
};

export default function IngestionPanel() {
  const [status, setStatus] = useState<Status>("IDLE");
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = async () => {
    const res = await fetch("/api/ingest/status");
    const data = await res.json();
    setStatus(data.status);
    if (data.status !== "RUNNING") {
      if (pollRef.current) clearInterval(pollRef.current);
    }
  };

  useEffect(() => {
    fetchStatus();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await fetch("/api/ingest/trigger", { method: "POST" });
      setStatus("RUNNING");
      pollRef.current = setInterval(fetchStatus, 10_000);
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
      <span style={{
        fontSize: "0.8rem",
        fontWeight: 600,
        color: STATUS_COLORS[status],
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}>
        {status}
      </span>
      <button
        onClick={handleTrigger}
        disabled={triggering || status === "RUNNING"}
        style={{
          background: "#333",
          color: "#f0f0f0",
          border: "none",
          borderRadius: "4px",
          padding: "0.35rem 0.8rem",
          cursor: status === "RUNNING" ? "not-allowed" : "pointer",
          fontSize: "0.85rem",
          opacity: status === "RUNNING" ? 0.5 : 1,
        }}
      >
        {triggering ? "Starting..." : "Start ingestion"}
      </button>
    </div>
  );
}
