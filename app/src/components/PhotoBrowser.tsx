"use client";

import { useState } from "react";
import Timeline, { Tile } from "./Timeline";
import Lightbox from "./Lightbox";
import type { Photo } from "@/lib/photo";
import { localDayRange } from "@/lib/search-params";

type Results =
  | { state: "idle" }
  | { state: "searching"; query: string }
  | { state: "done"; query: string; photos: Photo[] }
  | { state: "failed"; query: string; error: string };

/**
 * The Timeline with a search box above it. A search shows its matches, best first, in place of the
 * Timeline; clearing it brings the Timeline back where it was left.
 */
export default function PhotoBrowser() {
  const [query, setQuery] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [results, setResults] = useState<Results>({ state: "idle" });
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return clear();
    setResults({ state: "searching", query: q });
    const params = new URLSearchParams({ q });
    const range = localDayRange(from, to);
    if (range.from) params.set("from", range.from);
    if (range.to) params.set("to", range.to);
    try {
      const res = await fetch(`/api/search?${params}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setResults({ state: "done", query: q, photos: data.photos });
    } catch (err) {
      console.error("[PhotoBrowser] search failed", err);
      setResults({ state: "failed", query: q, error: (err as Error).message });
    }
  }

  function clear() {
    setQuery("");
    setFrom("");
    setTo("");
    setResults({ state: "idle" });
  }

  const searching = results.state !== "idle";
  const photos = results.state === "done" ? results.photos : [];

  return (
    <>
      <form onSubmit={search} style={{
        display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", padding: "12px 16px 4px",
      }}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search photos, e.g. kids on a beach at sunset"
          maxLength={500}
          aria-label="Search photos"
          style={{ ...fieldStyle, flex: "1 1 260px" }}
        />
        <label style={labelStyle}>
          From <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={fieldStyle} />
        </label>
        <label style={labelStyle}>
          To <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={fieldStyle} />
        </label>
        <button type="submit" disabled={results.state === "searching"} style={buttonStyle}>Search</button>
        {searching && <button type="button" onClick={clear} style={buttonStyle}>Back to timeline</button>}
      </form>

      {searching && (
        <div style={{ padding: "0 12px 48px" }}>
          <p style={{ padding: "10px 4px", color: "#999", fontSize: "0.85rem" }}>
            {results.state === "searching" && <>Searching for &ldquo;{results.query}&rdquo;… (the first search after a while takes ~20s)</>}
            {results.state === "failed" && <>Search failed: {results.error}</>}
            {results.state === "done" && (photos.length
              ? <>Best matches for &ldquo;{results.query}&rdquo;, closest first</>
              : <>No photos matched &ldquo;{results.query}&rdquo;</>)}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {photos.map((photo, i) => <Tile key={photo.id} photo={photo} onOpen={() => setLightboxIndex(i)} />)}
            <div style={{ flexGrow: 1000 }} />
          </div>
        </div>
      )}

      <div style={{ display: searching ? "none" : undefined }}>
        <Timeline />
      </div>

      {lightboxIndex !== null && results.state === "done" && (
        <Lightbox
          photos={photos}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onCoverChanged={(oldCoverId, cover) => setResults({
            ...results, photos: photos.map((p) => (p.id === oldCoverId ? cover : p)),
          })}
        />
      )}
    </>
  );
}

const fieldStyle: React.CSSProperties = {
  background: "#262626", color: "#f0f0f0", border: "1px solid #3a3a3a", borderRadius: 4,
  padding: "0.45rem 0.6rem", fontSize: "0.9rem", colorScheme: "dark",
};

const labelStyle: React.CSSProperties = { display: "flex", gap: 6, alignItems: "center", color: "#999", fontSize: "0.85rem" };

const buttonStyle: React.CSSProperties = {
  background: "#333", color: "#f0f0f0", border: "none", borderRadius: 4,
  padding: "0.5rem 1rem", cursor: "pointer",
};
