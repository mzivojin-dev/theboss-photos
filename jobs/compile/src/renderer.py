"""
Renders an Edit Plan with ffmpeg, keeping as much of the footage's quality as it can:

- Portrait or landscape to match most of the footage, so phone clips fill the frame.
- HDR kept as 10-bit HEVC in HLG when most footage is HLG; SDR clips and photos are converted
  into it. Otherwise 8-bit H.264.
- Every clip is encoded once: segments share one format and are joined without re-encoding, and
  the music is mixed in with the picture copied.
"""
import os
from dataclasses import dataclass

from .edit_plan import Clip, EditPlan, Segment
from .ffmpeg import duration_of, run

FPS = 30
TITLE_SECONDS = 3.5
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SILENCE = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]

# SDR into HLG: linear light with SDR white at 203 nits (BT.2408), then HLG. The regular scaler
# goes to RGB first because it knows each input's range and matrix (JPEGs are full range).
SDR_TO_HLG = ("format=gbrpf32le,zscale=tin=bt709:pin=bt709:min=gbr:rin=pc:t=linear:npl=203:p=bt709,"
              "zscale=tin=linear:pin=bt709:min=gbr:rin=pc:t=arib-std-b67:p=bt2020:m=bt2020nc:r=tv:npl=1000,"
              "format=yuv420p10le")
HLG_TO_SDR = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
              "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")

MUSIC_DIR = os.environ.get("MUSIC_DIR", "/app/music")
# Public domain (CC0) on OpenGameArt; downloaded into the image by the Dockerfile. Played in this
# order, crossfaded and looped as needed.
MUSIC = [
    ("relaxing_aug_4_2021.mp3", "Jazz Aug 4 2021 by Alex McCulloch (CC0)"),
    ("lofi_loop.ogg", "Lofi Hip Hop Loop by omfgdude (CC0)"),
]
MUSIC_VOLUME = 0.3
MUSIC_CROSSFADE = 4.0


@dataclass(frozen=True)
class Look:
    width: int
    height: int
    hdr: bool

    @staticmethod
    def for_clips(clips: list[Clip]) -> "Look":
        footage = sum(c.duration for c in clips) or 1.0
        portrait = sum(c.duration for c in clips if c.portrait) > footage / 2
        hdr = sum(c.duration for c in clips if c.hdr) > footage / 2
        return Look(1080, 1920, hdr) if portrait else Look(1920, 1080, hdr)

    @property
    def pix(self) -> str:
        return "yuv420p10le" if self.hdr else "yuv420p"

    @property
    def text_color(self) -> str:
        # Full white in HLG is the 1000-nit peak; HLG reference ("paper") white is about 75% signal.
        return "0xBFBFBF" if self.hdr else "white"

    @property
    def description(self) -> str:
        return f"{self.width}x{self.height} {'HDR HEVC (HLG)' if self.hdr else 'SDR H.264'}"

    @property
    def encode(self) -> list[str]:
        audio = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest"]
        if self.hdr:
            return ["-c:v", "libx265", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1",
                    "-x265-params", "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error",
                    "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc", *audio]
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", *audio]


@dataclass(frozen=True)
class Rendered:
    path: str
    seconds: float
    chapters: list[tuple[float, str]]  # (start in seconds, title), starting with the title card
    music_credits: list[str]


def render(plan: EditPlan, look: Look, workdir: str, music: bool = True) -> Rendered:
    parts = [_title_card(workdir, look, plan.title, plan.dates)]
    chapters = [(0.0, plan.title)]
    elapsed = TITLE_SECONDS
    n = 0
    for chapter in plan.chapters:
        chapters.append((elapsed, chapter.title))
        for segment in chapter.segments:
            n += 1
            part = _segment(workdir, look, n, segment)
            parts.append(part)
            elapsed += duration_of(part)
    listing = f"{workdir}/parts.txt"
    with open(listing, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    joined = f"{workdir}/joined.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy",
         "-movflags", "+faststart", joined])
    if not music:
        return Rendered(joined, elapsed, chapters, [])
    final = f"{workdir}/compilation.mp4"
    credits = _add_music(joined, final, elapsed)
    return Rendered(final, elapsed, chapters, credits)


def _text(look: Look, textfile: str, font: str, size: int, y: str, until: float | None = None,
          box: bool = True) -> str:
    f = f"drawtext=fontfile={font}:textfile={textfile}:fontsize={size}:fontcolor={look.text_color}:x=(w-tw)/2:y={y}"
    f += ":box=1:boxcolor=black@0.45:boxborderw=16" if box else ":shadowcolor=black@0.6:shadowx=3:shadowy=3"
    if until is not None:
        f += f":enable='lt(t,{until})'"
    return f


def _text_file(workdir: str, name: str, text: str) -> str:
    # drawtext reads text from a file, so captions need no escaping.
    path = f"{workdir}/{name}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _frame(look: Look, hdr_in: bool) -> str:
    """Fit any orientation into the frame over a blurred copy of itself, in the output's colour."""
    convert = ""
    if look.hdr and not hdr_in:
        convert = SDR_TO_HLG + ","
    elif hdr_in and not look.hdr:
        convert = HLG_TO_SDR + ","
    w, h = look.width, look.height
    # zscale needs even dimensions; some photos are odd (e.g. 1920x1083).
    return (f"[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2,{convert}format={look.pix},split[a][b];"
            f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3[bg];"
            f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,format={look.pix},setsar=1,fps={FPS}")


def _title_card(workdir: str, look: Look, title: str, dates: str) -> str:
    out = f"{workdir}/title.mp4"
    # DejaVu Sans Bold is about 0.65 em per character; keep the title within 90% of the frame width.
    size = min(84, int(look.width * 0.9 / (0.65 * max(1, len(title)))))
    t, d = _text_file(workdir, "title", title), _text_file(workdir, "dates", dates)
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=0x101418:s={look.width}x{look.height}:r={FPS}:d={TITLE_SECONDS}", *SILENCE,
         "-filter_complex", f"[0:v]format={look.pix},{_text(look, t, FONT_BOLD, size, '(h/2)-100', box=False)},"
                            f"{_text(look, d, FONT, 44, '(h/2)+30', box=False)},"
                            f"fade=t=in:st=0:d=0.5,fade=t=out:st={TITLE_SECONDS - 0.5}:d=0.5[v]",
         "-map", "[v]", "-map", "1:a", "-t", f"{TITLE_SECONDS}", *look.encode, out])
    return out


def _segment(workdir: str, look: Look, n: int, segment: Segment) -> str:
    out = f"{workdir}/segment{n:03}.mp4"
    length = segment.length
    if isinstance(segment.source, Clip):
        clip = segment.source
        video = _frame(look, clip.hdr)
        inputs = ["-ss", f"{segment.start:.2f}", "-t", f"{length:.2f}", "-i", clip.path]
        audio_input = "0:a" if clip.has_audio else "1:a"
        if not clip.has_audio:
            inputs += SILENCE
    else:
        frames = int(length * FPS)
        # A slow zoom on the photo, drawn at twice the size so it doesn't stutter.
        video = (_frame(look, hdr_in=False) + f",scale={look.width * 2}:{look.height * 2},"
                 f"zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1"
                 f":s={look.width}x{look.height}:fps={FPS},format={look.pix}")
        inputs = ["-loop", "1", "-framerate", f"{FPS}", "-t", f"{length:.2f}", "-i", segment.source.path, *SILENCE]
        audio_input = "1:a"
    if segment.chapter_title:
        video += "," + _text(look, _text_file(workdir, f"chapter{n:03}", segment.chapter_title), FONT_BOLD, 64,
                             "120", until=min(3.0, length), box=False)
    if segment.caption:
        video += "," + _text(look, _text_file(workdir, f"caption{n:03}", segment.caption), FONT, 40, "h-th-140",
                             until=min(3.5, length))
    fade_out = max(0.0, length - 0.3)
    video += f",fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out:.2f}:d=0.3[v]"
    audio = f"[{audio_input}]aresample=48000,afade=t=in:d=0.3,afade=t=out:st={fade_out:.2f}:d=0.3[a]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", f"{video};{audio}",
         "-map", "[v]", "-map", "[a]", "-t", f"{length:.2f}", *look.encode, out])
    return out


def _add_music(video_in: str, video_out: str, seconds: float) -> list[str]:
    """Mix a music bed under the clips' own sound, ducked while they make noise. The picture is
    copied, not re-encoded. Returns the credits of the tracks used."""
    inputs, credits, total = [], [], 0.0
    while total < seconds + MUSIC_CROSSFADE:
        filename, credit = MUSIC[len(credits) % len(MUSIC)]
        path = os.path.join(MUSIC_DIR, filename)
        inputs += ["-i", path]
        credits.append(credit)
        total += duration_of(path) - MUSIC_CROSSFADE
    graph = "[1:a]aformat=sample_rates=48000:channel_layouts=stereo[m1]"
    for k in range(2, len(credits) + 1):
        graph += (f";[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo[t{k}]"
                  f";[m{k - 1}][t{k}]acrossfade=d={MUSIC_CROSSFADE}[m{k}]")
    graph += (f";[m{len(credits)}]atrim=0:{seconds:.2f},afade=t=in:d=2,"
              f"afade=t=out:st={max(0.0, seconds - 4):.2f}:d=4,volume={MUSIC_VOLUME}[music]"
              f";[0:a]asplit[clip][key]"
              f";[music][key]sidechaincompress=threshold=0.02:ratio=6:attack=80:release=900[ducked]"
              f";[clip][ducked]amix=inputs=2:duration=first:normalize=0[a]")
    run(["ffmpeg", "-v", "error", "-y", "-i", video_in, *inputs, "-filter_complex", graph,
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", video_out])
    return list(dict.fromkeys(credits))
