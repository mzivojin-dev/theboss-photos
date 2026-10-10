"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Lightbox from "./Lightbox";
import type { Photo } from "@/lib/photo";

const ROW_HEIGHT = 220;

interface Day {
  key: string;
  label: string;
  /** Index into the photo list of the day's first photo, so a tile knows what to open. */
  start: number;
  photos: Photo[];
}

function groupByDay(photos: Photo[]): Day[] {
  const days: Day[] = [];
  photos.forEach((photo, idx) => {
    const date = new Date(photo.takenAt);
    const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
    const last = days[days.length - 1];
    if (last && last.key === key) {
      last.photos.push(photo);
    } else {
      const label = date.toLocaleDateString(undefined, {
        weekday: "long", day: "numeric", month: "long", year: "numeric",
      });
      days.push({ key, label, start: idx, photos: [photo] });
    }
  });
  return days;
}

export default function Timeline() {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const cursorRef = useRef<string | null>(null);
  const busyRef = useRef(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const loadMore = useCallback(async () => {
    if (busyRef.current || done) return;
    busyRef.current = true;
    setLoading(true);
    setFailed(false);
    try {
      const cursor = cursorRef.current;
      const res = await fetch(cursor ? `/api/photos?cursor=${encodeURIComponent(cursor)}` : "/api/photos");
      if (!res.ok) {
        console.error("[Timeline] fetch failed", res.status, await res.text());
        setFailed(true);
        return;
      }
      const data = await res.json();
      cursorRef.current = data.nextCursor;
      setPhotos((prev) => {
        const seen = new Set(prev.map((p) => p.id));
        return [...prev, ...data.photos.filter((p: Photo) => !seen.has(p.id))];
      });
      if (data.nextCursor === null) setDone(true);
    } catch (err) {
      console.error("[Timeline] fetch failed", err);
      setFailed(true);
    } finally {
      busyRef.current = false;
      setLoading(false);
    }
  }, [done]);

  // Start loading the next page well before the bottom, so scrolling never waits for it.
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || failed) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore(); },
      { rootMargin: "1500px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [loadMore, failed, photos.length]);

  const days = useMemo(() => groupByDay(photos), [photos]);

  return (
    <>
      <div style={{ padding: "0 12px 48px" }}>
        {days.map((day) => (
          <section
            key={day.key}
            style={{ contentVisibility: "auto", containIntrinsicSize: `auto ${ROW_HEIGHT * 2}px` }}
          >
            <h2 style={{
              position: "sticky", top: 0, zIndex: 2, padding: "14px 4px 8px",
              background: "linear-gradient(#1a1a1a 70%, rgba(26,26,26,0))",
              fontSize: "0.95rem", fontWeight: 600, color: "#ddd",
            }}>
              {day.label}
              <span style={{ marginLeft: 10, fontWeight: 400, color: "#777", fontSize: "0.8rem" }}>
                {day.photos.length}
              </span>
            </h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {day.photos.map((photo, i) => (
                <Tile key={photo.id} photo={photo} onOpen={() => setLightboxIndex(day.start + i)} />
              ))}
              <div style={{ flexGrow: 1000 }} />
            </div>
          </section>
        ))}

        {photos.length === 0 && loading && <SkeletonRows />}
        {photos.length > 0 && loading && (
          <div style={{ textAlign: "center", padding: "1.5rem", color: "#777", fontSize: "0.85rem" }}>
            Loading more…
          </div>
        )}
        {failed && (
          <div style={{ textAlign: "center", padding: "1.5rem" }}>
            <button onClick={loadMore} style={retryStyle}>Couldn&rsquo;t load photos. Try again</button>
          </div>
        )}
        {done && photos.length === 0 && (
          <div style={{ textAlign: "center", padding: "3rem", color: "#777" }}>No photos yet.</div>
        )}
        <div ref={sentinelRef} style={{ height: 1 }} />
      </div>

      {lightboxIndex !== null && (
        <Lightbox
          photos={photos}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onCoverChanged={(oldCoverId, cover) =>
            setPhotos((prev) => prev.map((p) => (p.id === oldCoverId ? cover : p)))}
        />
      )}
    </>
  );
}

/** A photo sized to its shape, so each row fills the width without cropping. */
function Tile({ photo, onOpen }: { photo: Photo; onOpen: () => void }) {
  const [loaded, setLoaded] = useState(false);
  const ratio = photo.width && photo.height ? photo.width / photo.height : 4 / 3;
  const stacked = (photo.groupSize ?? 0) > 1;

  return (
    <div
      onClick={photo.previewUrl ? onOpen : undefined}
      style={{
        position: "relative",
        flexGrow: ratio * 100,
        flexBasis: ratio * ROW_HEIGHT,
        maxWidth: ratio * ROW_HEIGHT * 2.2,
        cursor: photo.previewUrl ? "pointer" : "default",
        background: "#262626",
        borderRadius: 3,
        // A group reads as a small stack: two cards peeking out behind the cover.
        boxShadow: stacked ? "3px 3px 0 -1px #3a3a3a, 6px 6px 0 -2px #2e2e2e" : undefined,
        marginRight: stacked ? 6 : 0,
        marginBottom: stacked ? 6 : 0,
      }}
    >
      <div style={{ paddingBottom: `${100 / ratio}%` }} />
      {photo.previewUrl ? (
        <img
          src={photo.previewUrl}
          alt=""
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          style={{
            position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover",
            borderRadius: 3, opacity: loaded ? 1 : 0, transition: "opacity 300ms ease",
          }}
        />
      ) : (
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "#666" }}>
          &#9654;
        </div>
      )}
      {stacked && (
        <span style={{
          position: "absolute", right: 6, bottom: 6, padding: "2px 8px", borderRadius: 999,
          background: "rgba(0,0,0,0.65)", color: "#fff", fontSize: "0.75rem", fontWeight: 600,
          backdropFilter: "blur(4px)",
        }}>
          +{(photo.groupSize ?? 1) - 1}
        </span>
      )}
    </div>
  );
}

function SkeletonRows() {
  const ratios = [1.5, 0.75, 1.33, 1.78, 1, 1.5, 0.75, 1.33];
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, paddingTop: 48 }}>
      {ratios.map((ratio, i) => (
        <div key={i} style={{
          flexGrow: ratio * 100, flexBasis: ratio * ROW_HEIGHT, height: ROW_HEIGHT,
          background: "#262626", borderRadius: 3, animation: "pulse 1.4s ease-in-out infinite",
        }} />
      ))}
    </div>
  );
}

const retryStyle: React.CSSProperties = {
  background: "#333", color: "#f0f0f0", border: "none", borderRadius: 4,
  padding: "0.5rem 1rem", cursor: "pointer",
};
