"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Lightbox from "./Lightbox";

interface Photo {
  id: string;
  takenAt: string;
  previewUrl: string;
  width: number;
  height: number;
}

export default function Timeline() {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    try {
      const url = cursor ? `/api/photos?cursor=${cursor}` : "/api/photos";
      const res = await fetch(url);
      const data = await res.json();
      setPhotos((prev) => [...prev, ...data.photos]);
      setCursor(data.nextCursor);
      setHasMore(data.nextCursor !== null);
    } finally {
      setLoading(false);
    }
  }, [cursor, loading, hasMore]);

  useEffect(() => {
    loadMore();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadMore(); },
      { rootMargin: "400px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [loadMore]);

  return (
    <>
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
        gap: "2px",
        padding: "2px",
      }}>
        {photos.map((photo, idx) => (
          <div
            key={photo.id}
            onClick={() => setLightboxIndex(idx)}
            style={{ cursor: "pointer", aspectRatio: `${photo.width}/${photo.height}`, overflow: "hidden", background: "#2a2a2a" }}
          >
            <img
              src={photo.previewUrl}
              alt=""
              loading="lazy"
              style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            />
          </div>
        ))}
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: "2rem", color: "#888" }}>Loading...</div>
      )}
      <div ref={sentinelRef} style={{ height: "1px" }} />

      {lightboxIndex !== null && (
        <Lightbox
          photos={photos}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </>
  );
}
