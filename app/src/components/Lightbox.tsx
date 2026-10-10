"use client";

import { useState, useEffect, useRef } from "react";
import type { Photo } from "@/lib/photo";

interface Props {
  photos: Photo[];
  initialIndex: number;
  onClose: () => void;
  /** The user made `photo` the cover of the group whose cover was `oldCoverId`. */
  onCoverChanged: (oldCoverId: string, photo: Photo) => void;
}

/** Steps through the timeline; a cover also shows the similar photos behind it as a strip. */
export default function Lightbox({ photos, initialIndex, onClose, onCoverChanged }: Props) {
  const [index, setIndex] = useState(initialIndex);
  const [groups, setGroups] = useState<Record<string, Photo[]>>({});
  const [picked, setPicked] = useState(0);
  const [failed, setFailed] = useState<string | null>(null); // the cover whose group couldn't be loaded
  const [attempt, setAttempt] = useState(0);
  const [pinning, setPinning] = useState(false);
  const memberCount = useRef(0);
  const photo = photos[index];
  const isGroup = (photo.groupSize ?? 0) > 1;
  const members = isGroup ? groups[photo.id]?.filter((m) => m.previewUrl) : undefined;
  const shown = members?.[picked] ?? photo;
  memberCount.current = members?.length ?? 0;

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
      } else if (e.key === "ArrowDown") {
        setPicked((i) => Math.min(memberCount.current - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        setPicked((i) => Math.max(0, i - 1));
      } else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [photos.length, onClose]);

  useEffect(() => {
    if (!isGroup || groups[photo.id]) return;
    let current = true;
    setFailed(null);
    fetch(`/api/photos/${photo.id}/group`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data) => current && setGroups((prev) => ({ ...prev, [photo.id]: data.photos })))
      .catch((err) => {
        console.error("[Lightbox] group fetch failed", err);
        if (current) setFailed(photo.id);
      });
    return () => { current = false; };
  }, [photo.id, isGroup, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  const useAsCover = async () => {
    setPinning(true);
    try {
      const res = await fetch(`/api/photos/${shown.id}/cover`, { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
      const { photo: cover } = await res.json();
      setGroups((prev) => {
        const { [photo.id]: _old, ...rest } = prev;
        return rest;
      });
      setPicked(0);
      onCoverChanged(photo.id, cover);
    } catch (err) {
      console.error("[Lightbox] could not change the cover", err);
    } finally {
      setPinning(false);
    }
  };

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
          <div style={{ display: "flex", gap: 6, justifyContent: "center", alignItems: "center", padding: "10px 0 0", overflowX: "auto" }}>
            {(members ?? []).map((m, i) => (
              <img
                key={m.id}
                src={m.previewUrl!}
                alt=""
                onClick={() => setPicked(i)}
                style={{
                  height: 56, borderRadius: 3, cursor: "pointer", flexShrink: 0,
                  opacity: i === picked ? 1 : 0.55,
                  outline: i === picked ? "2px solid #fff" : "none",
                }}
              />
            ))}
            {!members && failed !== photo.id && (
              <span style={{ color: "#888", fontSize: "0.8rem" }}>Loading similar photos…</span>
            )}
            {!members && failed === photo.id && (
              <button onClick={() => setAttempt((n) => n + 1)} style={btnStyle}>
                Couldn&rsquo;t load similar photos. Try again
              </button>
            )}
            {members && picked > 0 && (
              <button onClick={useAsCover} disabled={pinning} style={{ ...btnStyle, marginLeft: 8, flexShrink: 0 }}>
                Use as cover
              </button>
            )}
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
