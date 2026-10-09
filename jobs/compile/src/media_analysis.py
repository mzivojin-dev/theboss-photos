"""
Measures clips and photos for the edit: ffprobe for what a clip is, one ffmpeg pass for how each
second looks and sounds, and OpenCV's YuNet face detector for how many clear faces a photo has.
"""
import json
import os
import re
import tempfile
from collections import defaultdict

import cv2

from .edit_plan import Clip, Photo, Signal
from .ffmpeg import run
from .media_item import MediaItem

FACE_MODEL = os.environ.get("FACE_MODEL", "/app/face_detection_yunet.onnx")
# Faces smaller than this share of the picture are background people and don't count.
MIN_FACE_AREA = 0.004
HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}


def analyse_clip(item: MediaItem, path: str) -> Clip:
    info = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    # Phones store portrait video as landscape plus a +-90 degree rotation.
    rotated = any(abs(int(d.get("rotation", 0))) == 90 for d in video.get("side_data_list", []))
    return Clip(
        item=item,
        path=path,
        duration=float(info["format"]["duration"]),
        has_audio=has_audio,
        hdr=video.get("color_transfer") in HDR_TRANSFERS,
        portrait=(video["height"] > video["width"]) != rotated,
        signals=_signals(path, has_audio),
    )


def _signals(path: str, has_audio: bool) -> dict[int, Signal]:
    """Per second: brightness and frame difference (motion) at 4 fps, and loudness."""
    values: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with tempfile.TemporaryDirectory() as tmp:
        video_log, audio_log = f"{tmp}/video.txt", f"{tmp}/audio.txt"
        graph = f"[0:v]fps=4,scale=320:-2,signalstats,metadata=print:file={video_log}[v]"
        maps = ["-map", "[v]"]
        if has_audio:
            graph += (f";[0:a]asetnsamples=12000,astats=metadata=1:reset=1,"
                      f"ametadata=print:key=lavfi.astats.Overall.RMS_level:file={audio_log}[a]")
            maps += ["-map", "[a]"]
        run(["ffmpeg", "-v", "error", "-i", path, "-filter_complex", graph, *maps, "-f", "null", "-"])
        for log, keys in ((video_log, {"YAVG", "YDIF", "YBITDEPTH"}), (audio_log, {"RMS_level"})):
            if not os.path.exists(log):
                continue
            second = 0
            for line in open(log):
                if line.startswith("frame:"):
                    # A clip with an edit list can start slightly before zero (pts_time:-0.021).
                    second = max(0, int(float(re.search(r"pts_time:(-?[\d.]+)", line).group(1))))
                elif "=" in line:
                    key, value = line.strip().rsplit("=", 1)
                    key = key.rsplit(".", 1)[-1]
                    if key in keys and value not in {"-inf", "inf", "nan"}:
                        values[second][key].append(float(value))

    def mean(v: dict[str, list[float]], key: str, default: float) -> float:
        return sum(v[key]) / len(v[key]) if v.get(key) else default

    signals = {}
    for second, v in values.items():
        scale = 2 ** (v["YBITDEPTH"][0] - 8) if v.get("YBITDEPTH") else 1  # 10-bit HDR reads 4x larger
        signals[second] = Signal(
            brightness=mean(v, "YAVG", 128 * scale) / (255 * scale),
            motion=mean(v, "YDIF", 0) / scale,
            loudness=mean(v, "RMS_level", -60),
        )
    return signals


_detector = None


def analyse_photo(item: MediaItem, path: str) -> Photo:
    faces, score = faces_in(path)
    return Photo(item=item, path=path, faces=faces, face_score=score)


def faces_in(path: str) -> tuple[int, float]:
    """How many clear faces a photo has, and a 0-1 score that grows with their size."""
    global _detector
    image = cv2.imread(path)
    if image is None:
        return 0, 0.0
    height, width = image.shape[:2]
    scale = 640 / max(height, width)
    small = cv2.resize(image, (round(width * scale), round(height * scale)))
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(FACE_MODEL, "", (640, 640), score_threshold=0.8)
    _detector.setInputSize((small.shape[1], small.shape[0]))
    _, faces = _detector.detect(small)
    if faces is None:
        return 0, 0.0
    areas = [face[2] * face[3] / (small.shape[0] * small.shape[1]) for face in faces]
    clear = [a for a in areas if a >= MIN_FACE_AREA]
    # Up to about four medium faces, or one close-up, fill the score.
    return len(clear), min(1.0, sum(min(a, 0.05) for a in clear) / 0.08)
