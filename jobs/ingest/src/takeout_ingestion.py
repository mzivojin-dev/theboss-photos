"""
Matches media in Takeout Archives to their Sidecars and hands each pair to the indexer.
"""
import logging
from dataclasses import dataclass
from typing import Callable

from .drive_zip_streamer import DriveZipStreamer, ZipEntry, find_matching_sidecar
from .sidecar_parser import PhotoMetadata, parse as parse_sidecar

log = logging.getLogger(__name__)


@dataclass
class TakeoutArchive:
    file_id: str
    name: str
    streamer: DriveZipStreamer


def ingest_archives(
    archives: list[TakeoutArchive],
    index_media: Callable[[ZipEntry, PhotoMetadata], None],
    archive_fully_ingested: Callable[[TakeoutArchive], None],
) -> None:
    # Takeout splits an export across archives, and a media file's Sidecar is often in a
    # different archive than the media itself, so collect every archive's Sidecars first.
    sidecars: dict[str, bytes] = {}
    for archive in archives:
        for entry in archive.streamer.list_entries():
            if entry.is_sidecar:
                sidecars[entry.name] = entry.read()

    for archive in archives:
        log.info("Processing archive: %s (%s)", archive.name, archive.file_id)
        skipped = 0

        for entry in archive.streamer.list_entries():
            if not entry.is_image and not entry.is_video:
                continue

            # Match sidecar by canonical filename, ignoring case and duplicate suffixes.
            sidecar_bytes = find_matching_sidecar(entry.name.split("/")[-1], sidecars)
            if sidecar_bytes is None:
                log.warning("No sidecar for %s — skipping", entry.name)
                skipped += 1
                continue

            try:
                metadata = parse_sidecar(sidecar_bytes)
            except ValueError as e:
                log.warning("Sidecar parse error for %s: %s — skipping", entry.name, e)
                skipped += 1
                continue

            index_media(entry, metadata)

        # Keep an archive with skipped media so deleting it can't lose those files.
        if skipped:
            log.warning("Keeping archive %s: %d media file(s) skipped", archive.name, skipped)
        else:
            archive_fully_ingested(archive)
