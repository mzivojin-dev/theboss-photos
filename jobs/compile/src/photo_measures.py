"""
What grouping needs to know about a photo: a perceptual hash, how many clear faces it has, and how
sharp and well exposed it is. Stored on the Photo Index document as the `similar_*` fields, so a
photo is measured once.
"""
from typing import Optional

import cv2
import numpy as np

# The Photo Index fields `measure` returns.
MEASURE_FIELDS = ["similar_hash", "similar_faces", "similar_face_score", "similar_sharpness", "similar_exposure"]


def perceptual_hash(gray: np.ndarray) -> int:
    """64-bit pHash: the low frequencies of a 32x32 copy, each above or below their median."""
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8]
    bits = (low > np.median(low)).flatten()
    return int("".join("1" if bit else "0" for bit in bits), 2)


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian on a 640px copy: higher is crisper."""
    scale = 640 / max(gray.shape)
    small = cv2.resize(gray, (round(gray.shape[1] * scale), round(gray.shape[0] * scale)))
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def exposure(gray: np.ndarray) -> float:
    """1 for a well-exposed photo, falling toward 0 when it is very dark or blown out."""
    mean = float(gray.mean()) / 255
    return max(0.0, 1 - max(0.0, 0.2 - mean) * 5 - max(0.0, mean - 0.85) * 5)


def measure(path: str) -> Optional[dict]:
    """The photo at `path` as Photo Index fields (plain Python types), or None if unreadable."""
    from .media_analysis import faces_in  # loads the face model, which only the real run has

    gray = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    faces, face_score = faces_in(path)
    return {
        "similar_hash": f"{perceptual_hash(gray):016x}",
        "similar_faces": int(faces),
        "similar_face_score": float(face_score),
        "similar_sharpness": sharpness(gray),
        "similar_exposure": exposure(gray),
    }
