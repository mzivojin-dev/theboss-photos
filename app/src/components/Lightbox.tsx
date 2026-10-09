"use client";

import { useState, useEffect, useRef } from "react";

export interface Photo {
  id: string;
  takenAt: string;
  previewUrl: string | null;
  width: number | null;
  height: number | null;
  /** On a group's cover: how many similar photos it stands for, itself included. */
  groupSize?: number | null;
}

interface Props {
  photos: Photo[];
  initialIndex: number;
  onClose: () => void;
}

/** Steps through the timeline; a cover also shows the similar photos behind it as a strip. */
export default function Lightbox({ photos, initialIndex, onClose }: Props) {
  const [index, setIndex] = useState(initialIndex);
  const [groups, setGroups] = useState<Record<string, Photo[]>>({});
  const [picked, setPicked] = useState(0);
  const requested = useRef(new Set<string>());
  const photo = photos[index];
  const isGroup = (photo.groupSize ?? 0) > 1;
  const members = isGroup ? groups[photo.id] : undefined;
  const shown = members?.[picked] ?? photo;

  const go = (to: number) => {
    setIndex(Math.min(photos.length - 1, Math.max(0, to)));
    setPicked(0);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        setIndex((i) => Math.max(0, i - 1));
        setPicked(0);
      } else if (e.key === "ArrowRight") {
        setIndex((i) => Math.min(photos.length - 1, i + 1));
        setPicked(0);
      } else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [photos.length, onClose]);

  useEffect(() => {
    if (!isGroup || requested.current.has(photo.id)) return;
    requested.current.add(photo.id);
    fetch(`/api/photos/${photo.id}/group`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data) => setGroups((prev) => ({ ...prev, [photo.id]: data.photos })))
      .catch((err) => console.error("[Lightbox] group fetch failed", err));
  }, [photo.id, isGroup]);

  // Warm the neighbours so stepping is instant.
  useEffect(() => {
    for (const near of [photos[index - 1], photos[index + 1]]) {
      if (near?.previewUrl) new Image().src = near.previewUrl;
    }
  }, [index, photos]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.94)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000, animation: "fade-in 160ms ease",
      }}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ position: "relative", maxWidth: "92vw", maxHeight: "94vh" }}>
        {shown.previewUrl && (
          <img
            key={shown.id}
            src={shown.previewUrl}
            alt=""
            style={{
              maxWidth: "92vw", maxHeight: members ? "72vh" : "82vh", objectFit: "contain",
              display: "block", margin: "0 auto", animation: "fade-in 200ms ease",
            }}
          />
        )}

        {isGroup && (
          <div style={{ display: "flex", gap: 6, justifyContent: "center", padding: "10px 0 0", overflowX: "auto" }}>
            {(members ?? []).map((m, i) => (
              <img
                key={m.id}
                src={m.previewUrl ?? ""}
                alt=""
                onClick={() => setPicked(i)}
                style={{
                  height: 56, borderRadius: 3, cursor: "pointer", flexShrink: 0,
                  opacity: i === picked ? 1 : 0.55,
                  outline: i === picked ? "2px solid #fff" : "none",
                }}
              />
            ))}
            {!members && <span style={{ color: "#888", fontSize: "0.8rem" }}>Loading similar photos…</span>}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem 0" }}>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={() => go(index - 1)} disabled={index === 0} style={btnStyle}>&larr;</button>
            <button onClick={() => go(index + 1)} disabled={index === photos.length - 1} style={btnStyle}>&rarr;</button>
          </div>
          <span style={{ color: "#aaa", fontSize: "0.85rem" }}>
            {new Date(shown.takenAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
            &nbsp; {index + 1} / {photos.length}
            {members && ` · similar ${picked + 1}/${members.length}`}
          </span>
          <a
            href={`/api/photos/${shown.id}/download`}
            style={{ ...btnStyle, textDecoration: "none" }}
          >
            Download original
          </a>
        </div>
      </div>

      <button onClick={onClose} style={{ position: "fixed", top: "1rem", right: "1rem", ...btnStyle }}>
        &times;
      </button>
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: "#333",
  color: "#f0f0f0",
  border: "none",
  borderRadius: "4px",
  padding: "0.4rem 0.9rem",
  cursor: "pointer",
  fontSize: "0.9rem",
};
