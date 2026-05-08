"use client";

import { useState, useEffect, useRef } from "react";

function buildBookmarklet(appOrigin: string): string {
  // 1. Extract download URLs from the Takeout page.
  // 2. Try postMessage to window.opener (works if opener isn't nulled by COOP).
  // 3. Fall back to a fetch POST to the local handoff endpoint (works always,
  //    since Chrome treats http://localhost as a secure context even from HTTPS).
  const code =
    `(async function(){` +
    `var L=[...document.querySelectorAll('a[href*="takeout/download"]')];` +
    `if(!L.length){alert('No Takeout download links found on this page.');return;}` +
    `var urls=L.map(function(a){return a.href;});` +
    `var ck=document.cookie;` +
    `var sent=false;` +
    `if(window.opener){` +
    `  try{window.opener.postMessage({type:'takeout-links',urls:urls,cookies:ck},'${appOrigin}');sent=true;}` +
    `  catch(e){}` +
    `}` +
    `if(!sent){` +
    `  try{` +
    `    await fetch('${appOrigin}/api/ingest/local/handoff',{` +
    `      method:'POST',headers:{'Content-Type':'application/json'},` +
    `      body:JSON.stringify({urls:urls,cookies:ck}),mode:'cors'` +
    `    });` +
    `    sent=true;` +
    `  }catch(e){}` +
    `}` +
    `if(sent){alert('Sent '+urls.length+' link(s) to the ingest page.');}` +
    `else{alert('Could not reach the ingest page. Make sure the app is running at ${appOrigin}.');}` +
    `})();`;
  return `javascript:${code}`;
}

export default function LocalIngestPage() {
  const [takeoutUrl, setTakeoutUrl] = useState("https://takeout.google.com/takeout/downloads");
  const [folder, setFolder] = useState("");
  const [processing, setProcessing] = useState(false);
  const [folderError, setFolderError] = useState("");
  const [log, setLog] = useState<{ text: string; type: string }[]>([]);
  const [receivedUrls, setReceivedUrls] = useState<string[]>([]);
  const [receivedCookies, setReceivedCookies] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const bookmarkletRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    bookmarkletRef.current?.setAttribute("href", buildBookmarklet(window.location.origin));
    const isWin = navigator.platform.toLowerCase().includes("win");
    const home = isWin ? (process.env.USERPROFILE ?? "C:\\Users\\user") : "~";
    const sep = isWin ? "\\" : "/";
    setFolder(`${home}${sep}Downloads`);
  }, []);

  // Receive links via postMessage (when window.opener is available).
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.origin !== "https://takeout.google.com") return;
      const data = event.data as { type?: string; urls?: string[]; cookies?: string };
      if (data?.type !== "takeout-links" || !Array.isArray(data.urls)) return;
      setReceivedUrls(data.urls);
      setReceivedCookies(data.cookies ?? "");
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  // Receive links via SSE (fetch-fallback path) and general progress events.
  useEffect(() => {
    const es = new EventSource("/api/ingest/local/progress");
    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as {
          type: string;
          message: string;
          urls?: string[];
          cookies?: string;
        };
        if (event.type === "links") {
          setReceivedUrls(event.urls ?? []);
          setReceivedCookies(event.cookies ?? "");
          return;
        }
        setLog((prev) => [...prev, { text: event.message, type: event.type }]);
        if (event.message === "All ZIPs processed.") setProcessing(false);
      } catch {
        /* ignore */
      }
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [log]);

  const handleProcessUrls = async () => {
    if (!receivedUrls.length) return;
    setProcessing(true);
    const res = await fetch("/api/ingest/local/urls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: receivedUrls, cookies: receivedCookies }),
    });
    const data = await res.json();
    if (!res.ok) {
      setLog((prev) => [...prev, { text: data.error ?? "Unknown error", type: "error" }]);
      setProcessing(false);
    }
  };

  const handleProcessFolder = async () => {
    if (!folder.trim()) return;
    setFolderError("");
    setProcessing(true);
    const res = await fetch("/api/ingest/local/folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: folder.trim() }),
    });
    const data = await res.json();
    if (!res.ok) {
      setFolderError(data.error ?? "Unknown error");
      setProcessing(false);
    }
  };

  const logColor = (type: string) => {
    if (type === "error") return "#f44336";
    if (type === "done") return "#4caf50";
    if (type === "start") return "#f0a500";
    return "#d0d0d0";
  };

  const shared = {
    input: {
      flex: 1,
      background: "#1a1a1a",
      color: "#f0f0f0",
      border: "1px solid #444",
      borderRadius: "4px",
      padding: "0.4rem 0.6rem",
      fontSize: "0.85rem",
    } as React.CSSProperties,
    btn: {
      background: "#333",
      color: "#f0f0f0",
      border: "none",
      borderRadius: "4px",
      padding: "0.4rem 0.8rem",
      cursor: "pointer",
      fontSize: "0.85rem",
    } as React.CSSProperties,
  };

  return (
    <main style={{ padding: "1.5rem", fontFamily: "monospace", maxWidth: "800px" }}>
      <h1 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: "1.5rem" }}>Local Ingest</h1>

      {/* Step 1 */}
      <section style={{ marginBottom: "1.5rem" }}>
        <p style={{ fontSize: "0.8rem", color: "#888", marginBottom: "0.5rem" }}>
          1. Open your Takeout downloads page (must be logged in to Google).
        </p>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input value={takeoutUrl} onChange={(e) => setTakeoutUrl(e.target.value)} style={shared.input} />
          <button onClick={() => window.open(takeoutUrl, "_blank")} style={shared.btn}>Open</button>
        </div>
      </section>

      {/* Step 2 */}
      <section style={{ marginBottom: "1.5rem" }}>
        <p style={{ fontSize: "0.8rem", color: "#888", marginBottom: "0.5rem" }}>
          2. Drag this bookmarklet to your bookmarks bar, then click it on the Takeout page.
          It sends all download links to this page automatically.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <a
            ref={bookmarkletRef}
            href="#"
            onClick={(e) => e.preventDefault()}
            style={{
              display: "inline-block",
              background: "#2a2a2a",
              color: "#7eb8f7",
              border: "1px solid #444",
              borderRadius: "4px",
              padding: "0.4rem 0.9rem",
              fontSize: "0.85rem",
              textDecoration: "none",
              cursor: "grab",
            }}
          >
            Ingest Takeout
          </a>
          <span style={{ fontSize: "0.75rem", color: "#555" }}>← drag to bookmarks bar</span>
        </div>
      </section>

      {/* Received links */}
      {receivedUrls.length > 0 && (
        <section style={{ marginBottom: "1.5rem", borderLeft: "2px solid #4caf50", paddingLeft: "0.75rem" }}>
          <p style={{ fontSize: "0.8rem", color: "#4caf50", marginBottom: "0.5rem" }}>
            {receivedUrls.length} download link(s) received from Takeout.
          </p>
          <div
            style={{
              fontSize: "0.72rem",
              color: "#7eb8f7",
              marginBottom: "0.6rem",
              maxHeight: "80px",
              overflowY: "auto",
            }}
          >
            {receivedUrls.map((url, i) => (
              <div
                key={i}
                style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={url}
              >
                {url}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={handleProcessUrls}
              disabled={processing}
              style={{ ...shared.btn, opacity: processing ? 0.5 : 1 }}
            >
              {processing ? "Processing…" : `Process ${receivedUrls.length} URL(s)`}
            </button>
            <button
              onClick={() => { setReceivedUrls([]); setReceivedCookies(""); }}
              disabled={processing}
              style={{ ...shared.btn, background: "transparent", color: "#555", opacity: processing ? 0.5 : 1 }}
            >
              Clear
            </button>
          </div>
        </section>
      )}

      {/* Step 3 — folder fallback */}
      <section style={{ marginBottom: "1.5rem" }}>
        <p style={{ fontSize: "0.8rem", color: "#888", marginBottom: "0.5rem" }}>
          3. Alternatively, download ZIPs manually and process them from a local folder.
        </p>
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.3rem" }}>
          <input
            value={folder}
            onChange={(e) => { setFolder(e.target.value); setFolderError(""); }}
            placeholder="e.g. C:\Users\you\Downloads"
            style={shared.input}
          />
          <button
            onClick={handleProcessFolder}
            disabled={processing || !folder.trim()}
            style={{ ...shared.btn, opacity: processing || !folder.trim() ? 0.5 : 1 }}
          >
            {processing ? "Processing…" : "Process"}
          </button>
        </div>
        {folderError && (
          <p style={{ fontSize: "0.8rem", color: "#f44336", margin: "0.25rem 0 0" }}>{folderError}</p>
        )}
      </section>

      {/* Progress */}
      <section>
        <p style={{ fontSize: "0.8rem", color: "#888", marginBottom: "0.5rem" }}>Progress</p>
        <div
          ref={logRef}
          style={{
            background: "#0a0a0a",
            border: "1px solid #333",
            borderRadius: "4px",
            padding: "0.75rem",
            height: "380px",
            overflowY: "auto",
            fontSize: "0.78rem",
            lineHeight: "1.7",
          }}
        >
          {log.length === 0
            ? <span style={{ color: "#444" }}>Waiting for ingest events…</span>
            : log.map((entry, i) => (
                <div key={i} style={{ color: logColor(entry.type) }}>{entry.text}</div>
              ))
          }
        </div>
        {log.length > 0 && (
          <button
            onClick={() => setLog([])}
            style={{ marginTop: "0.5rem", background: "transparent", color: "#555", border: "none", cursor: "pointer", fontSize: "0.75rem", padding: 0 }}
          >
            Clear log
          </button>
        )}
      </section>
    </main>
  );
}
