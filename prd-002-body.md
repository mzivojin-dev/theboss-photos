## Problem Statement

Videos from Google Takeout archives are ingested and stored in GCS Archive (cold storage), but they are not viewable from the app. The `YouTubeUploader` module is fully implemented and tested but is disconnected from the ingestion pipeline. As a result, videos land in Firestore with `media_type: "video"` and no `youtube_video_id`, making them invisible in the Timeline. Users cannot watch their personal videos through the app even though those videos were the reason for exporting from Google Photos.

## Solution

Wire `YouTubeUploader` into the main ingestion pipeline so that each video encountered during a Takeout ingest is uploaded to YouTube (as unlisted) and its `youtube_video_id` is written to Firestore. Update the Timeline and Lightbox components to recognise `media_type: "video"` and render video thumbnails with inline YouTube embed playback, creating a unified photo-and-video timeline.

## User Stories

1. As a user ingesting a Takeout archive that contains videos, I want videos to be automatically uploaded to YouTube as unlisted during ingestion, so that they are privately accessible through the app.
2. As a user, I want video thumbnails to appear in the Timeline alongside photo previews, so that I have a unified chronological view of my memories.
3. As a user, I want to click a video thumbnail to play it inline in the Lightbox, so that I don't leave the app to watch my videos.
4. As a user, I want videos to be organised into monthly YouTube playlists (e.g., "2023-07"), so that my YouTube library stays structured and browsable outside the app.
5. As a user, I want already-uploaded videos to be skipped on a re-ingest (deduplication), so that I don't accumulate duplicates on YouTube or in Firestore.
6. As a user, I want video upload failures during ingestion to be logged and skipped (non-fatal), so that a single failed video doesn't abort the entire ingestion job.
7. As a user, I want a visual indicator on video thumbnails (e.g., a play icon overlay), so that I can distinguish videos from photos at a glance.
8. As a user, I want the Lightbox to navigate across both photos and videos, so that I can browse my timeline without switching between viewers.
9. As a user, I want a "Download original" link available for videos (from GCS Archive), so that I can retrieve my original video file if needed.
10. As a user, I want the ingestion job to continue processing remaining items in the ZIP if a video upload fails, so that a YouTube API quota error doesn't prevent all my photos from being indexed.
11. As a user, I want a video's `taken_at` timestamp (from the sidecar) to be preserved correctly in Firestore, so that the Timeline sorts correctly across both media types.
12. As an operator, I want the YouTube OAuth token to be stored and refreshed via GCP Secret Manager (`SecretManagerAuth`), so that the long-running Cloud Run Job can authenticate without manual intervention.
13. As an operator, I want the video upload feature to be gated behind an `ENABLE_YOUTUBE_UPLOAD` environment variable, so that the ingestion job can be deployed with or without YouTube upload without code changes.
14. As an operator setting up video support for the first time, I want clear documentation on how to seed the YouTube OAuth token into Secret Manager, so that I can configure it without writing code.

## Implementation Decisions

**Ingest pipeline (`main.py`)**
- `main.py` accepts an optional `video_uploader` dependency (default `None`); when `ENABLE_YOUTUBE_UPLOAD=true`, it is initialised as `YouTubeUploader(SecretManagerAuth(...))`.
- For each video entry in a ZIP: after the dedup check passes, call `video_uploader.upload(video_bytes, title, taken_at)` to obtain `youtube_video_id`; build a `PhotoDoc` with `media_type="video"`, `youtube_video_id` set, `preview_gcs_path=None`, `original_gcs_path` set (Archive write continues as today).
- Video upload errors are caught and logged at WARNING level; the video is skipped (not indexed) — same error-handling pattern as image parse errors today.
- When `ENABLE_YOUTUBE_UPLOAD=false` (default), videos are still written to GCS Archive and indexed with `media_type="video"` but `youtube_video_id=None`; the app filters them from the Timeline.

**YouTube credentials**
- OAuth token stored in Secret Manager under secret name configurable via `YOUTUBE_SECRET_NAME` env var on the Cloud Run Job (default: `youtube-oauth-token`).
- Terraform provisions the secret resource; initial token seeding is a one-time manual step: run the local `LocalTokenAuth` flow, then write the pickle bytes to Secret Manager.

**Firestore / PhotoDoc**
- `original_gcs_path` remains populated for videos (Archive write is unchanged).
- `youtube_video_id` is populated only on successful upload; `None` otherwise.
- No schema migration — existing video documents (currently `youtube_video_id=None`) are untouched; the Timeline filter handles them.

**Web app — `GET /api/photos`**
- Response surface gains `mediaType` and `youtubeVideoId` per item (already in Firestore; just need to be surfaced in the mapped response).
- Server-side filter: excludes documents where `media_type="video"` and `youtube_video_id` is null.

**Web app — Timeline**
- `PhotoResult` TypeScript interface gains `mediaType: "photo" | "video"` and `youtubeVideoId: string | null`.
- Video thumbnails use `https://img.youtube.com/vi/{youtubeVideoId}/hqdefault.jpg` as `src`; a play-button SVG overlay is composited via CSS `position: absolute`.

**Web app — Lightbox**
- For `mediaType: "video"`: renders an `<iframe>` YouTube embed (`youtube-nocookie.com`, `allow="autoplay"`) instead of `<img>`.
- For `mediaType: "photo"`: existing `<img>` path unchanged.
- Prev/next navigation and "Download original" work identically for both media types.

## Testing Decisions

Good tests assert observable behaviour (return values, Firestore writes, HTTP responses, rendered DOM nodes) against external boundaries only — not internal call sequences.

**Ingest pipeline**
- `test_main.py`: extend existing tests to cover the video branch — assert that `YouTubeUploader.upload` is called for `.mp4` entries and that the resulting `PhotoDoc` carries `youtube_video_id` and `original_gcs_path`. Assert that a `YouTubeUploader` exception causes the video to be skipped (no Firestore write) and does not abort remaining items.
- Prior art: `test_photo_index_repository_video.py` (video-specific Firestore fields), `test_youtube_uploader.py` (YouTube API contract already covered).

**Web app**
- `Timeline.test.tsx`: given a mix of `PhotoResult` items, assert video items render a play-icon overlay and YouTube thumbnail `src`.
- `Lightbox.test.tsx`: given a video `PhotoResult`, assert `<iframe>` is rendered (not `<img>`); photo path unchanged.
- `photos/route.test.ts`: assert documents with `youtubeVideoId=null` are excluded from the paginated response.
- Prior art: existing Jest tests in `app/src/__tests__/`.

## Out of Scope

- Automatic ingestion scheduling (Cloud Scheduler / Drive webhooks) — manual trigger remains.
- Video transcoding or server-side thumbnail generation — YouTube CDN thumbnails are used as-is.
- Multi-resolution streaming or adaptive bitrate — YouTube embed handles this.
- Face/object recognition or AI tagging.
- Migration of existing video documents that were indexed without `youtube_video_id`.
- Local CLI ingestion flow (`local_main.py`, currently unmerged).
- Video trimming, editing, or any in-app post-processing.

## Further Notes

- `YouTubeUploader` already handles playlist creation and caching; `main.py` only needs to call `.upload()` and store the returned `youtube_video_id`.
- YouTube's default quota is ~10,000 units/day (~6 video uploads/day at standard cost). Heavy archives may hit quota; the skip-on-error behaviour prevents a hard stop.
- `youtube-nocookie.com` embeds are used in the Lightbox to avoid setting third-party cookies on the app domain.
- The initial OAuth token (`LocalTokenAuth` pickle) requires a one-time interactive browser flow that cannot run inside the Cloud Run Job; it must be seeded locally before first deployment with `ENABLE_YOUTUBE_UPLOAD=true`.
