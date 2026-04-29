"use client";

import { useState, useEffect } from "react";

interface Photo {
  id: string;
  takenAt: string;
  previewUrl: string;
  width: number;
  height: number;
}

interface Props {
  photos: Photo[];
  initialIndex: number;
  onClose: () => void;
}

export default function Lightbox({ photos, initialIndex, onClose }: Props) {
  const [index, setIndex] = useState(initialIndex);
  const photo = photos[index];

  const prev = () => setIndex((i) => Math.max(0, i - 1));
  const next = () => setIndex((i) => Math.min(photos.length - 1, i + 1));

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.92)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ position: "relative", maxWidth: "90vw", maxHeight: "90vh" }}>
        <img
          src={photo.previewUrl}
          alt=""
          style={{ maxWidth: "90vw", maxHeight: "85vh", objectFit: "contain", display: "block" }}
        />

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem 0" }}>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button onClick={prev} disabled={index === 0} style={btnStyle}>&larr;</button>
            <button onClick={next} disabled={index === photos.length - 1} style={btnStyle}>&rarr;</button>
          </div>
          <span style={{ color: "#aaa", fontSize: "0.85rem" }}>
            {new Date(photo.takenAt).toLocaleDateString()} &nbsp; {index + 1} / {photos.length}
          </span>
          <a
            href={`/api/photos/${photo.id}/download`}
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
