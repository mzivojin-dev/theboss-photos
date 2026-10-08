"""
Makes one trip's Compilation: fetches its media, measures it, plans the edit, and renders it.
"""
import logging
from typing import Optional, Protocol

from .compilation_job import Made, Skipped
from .edit_plan import enough_footage, footage_seconds, plan_edit, segment_label
from .media_analysis import analyse_clip, analyse_photo
from .media_item import MediaItem
from .renderer import Look, render
from .trips import Trip

log = logging.getLogger(__name__)


class MediaSource(Protocol):
    def fetch(self, item: MediaItem, directory: str) -> Optional[str]: ...


class CompilationMaker:
    def __init__(self, media: MediaSource, music: bool = True):
        self._media = media
        self._music = music

    def __call__(self, trip: Trip, workdir: str) -> Made | Skipped:
        clips = [analyse_clip(item, path) for item, path in self._fetch(trip.clips, workdir)]
        if not enough_footage(clips):
            return Skipped(f"{len(clips)} clip(s), {footage_seconds(clips):.0f}s of footage")
        photos = [analyse_photo(item, path) for item, path in self._fetch(trip.photos, workdir)]
        log.info("  %d of %d photos have clear faces", sum(1 for p in photos if p.faces), len(photos))

        plan = plan_edit(trip, clips, photos)
        look = Look.for_clips(clips)
        log.info("  '%s' / '%s', %s, chapters: %s", plan.title, plan.dates, look.description,
                 ", ".join(c.title for c in plan.chapters))
        for chapter in plan.chapters:
            for segment in chapter.segments:
                log.info("    %s", segment_label(segment))
        rendered = render(plan, look, workdir, music=self._music)
        return Made(rendered=rendered, title=plan.title, dates=plan.dates, look=look.description,
                    clips=len(clips), photos=len(photos))

    def _fetch(self, items: list[MediaItem], workdir: str) -> list[tuple[MediaItem, str]]:
        fetched = []
        for item in items:
            path = self._media.fetch(item, workdir)
            if path is None:
                log.warning("  No staged copy, Original or Preview for %s; leaving it out", item.filename)
            else:
                fetched.append((item, path))
        return fetched
