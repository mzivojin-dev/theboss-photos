# theboss-photos — Domain Context

## Glossary

**Takeout Archive**
A `.zip` file produced by Google Takeout. Contains photos, videos, and `.json` sidecar files (metadata: timestamps, GPS, album membership). One Google export may produce multiple Takeout Archives. The source of truth for all media.

**Sidecar**
A `.json` file inside a Takeout Archive that carries metadata for a corresponding photo or video (timestamp, GPS coordinates, album name, etc.).

**Preview Image**
A resized, lower-quality version of a photo (~200KB), generated at ingestion time from the original. Stored in GCS Standard tier. Served to the browser for browsing/viewing.

**Original**
The full-resolution photo or video extracted from a Takeout Archive. Stored in GCS Archive tier as an individual object. Retrieved only when the user explicitly requests a download.

**Ingestion Job**
A Cloud Run Job that reads Takeout Archives from Google Drive via byte-range requests (no full ZIP download), extracts files in memory, generates Previews, and writes Previews and Originals to their respective GCS buckets. It also writes new media to Staging, and starts the Compilation Job after a run that indexed anything.

**Media Indexer**
The part of the Ingestion Job that indexes one media file (photo or video) from a Takeout Archive, given its Sidecar metadata: it skips files already in the Photo Index, writes the Original and (for photos) the Preview Image, then writes the Photo Index document last, so a document's presence means the file is fully indexed.

**Staging**
A Standard-storage GCS bucket where the Ingestion Job copies each newly indexed video, and a 1920px JPEG of each photo, while it has the bytes in memory. Lets the Compilation Job read media without Archive retrieval. Copies expire after 30 days.

**Trip**
A run of days on which something was taken more than 50 km from home, with at least one video. Home is the place with the most *days* of media (not the most media). A Trip ends only at a day with media at home, so days without photos don't split it; departure and return days are part of it. Days are local days: Sidecar times are UTC and are converted to the time zone where each item was taken.

**Compilation**
An edited video of one Trip: the best stretch of each clip (loud, some movement, not dark or shaky), photos that fill the gaps (preferring clear faces, one per burst), a chapter per local day, captions with place and time of day, and public-domain background music. Portrait or landscape, and HDR or SDR, follow most of the Trip's footage. A Trip gets a Compilation only with at least 3 clips or 60 seconds of footage.

**Compilation Job**
A Cloud Run Job that makes a Compilation for each Trip whose media changed since its last one. Started by the Ingestion Job after a run that indexed new media. No AI: highlights come from ffmpeg measurements and photos are ranked by face detection.

**Drive Folder**
A designated Google Drive folder owned by a single Google account (personal use). All Takeout Archives are placed here manually by the user before triggering an Ingestion Job.

## Storage

| Artifact | GCS Storage Class | Access pattern |
|---|---|---|
| Preview Image | Standard (private, served via signed URLs with 1hr TTL) | Every browse/view |
| Original | Archive | On-demand download only |
| Takeout Archive (source ZIP) | Not stored — discarded after ingestion | — |
| Staged media | Standard, deleted after 30 days | Read by the Compilation Job |
| Compilation | Standard (private) | Served by signed URL |

## Timeline UX

Infinite scroll — loads 50 photos per batch ordered by `taken_at` descending. Next batch triggered automatically when user scrolls to the bottom. Uses Firestore cursor pagination internally.

## MVP Scope

- Chronological timeline — scroll through photos ordered by date taken
- Lightbox — single photo view with previous/next navigation
- Download Original — triggers on-demand retrieval from Archive GCS

Out of scope for MVP: albums, map view, search, face/object tagging, video playback, shared access.

## Data Store

**Photo Index** — Cloud Firestore collection storing one document per photo or video, with `media_type` (`photo` | `video`), `taken_at` (timestamp), `preview_gcs_path`, `original_gcs_path`, `filename`, `width`, `height`, `google_photos_id` (from sidecar URL field). Queried for the timeline ordered by `taken_at`.

**Compilations** — Firestore collection with one document per Trip, keyed `<first day>_<last day>`: status (`rendering`, `ready`, `skipped`, `failed`), the membership hash of the Trip's media (a Compilation is made again when it changes), title, dates, chapters, music credits and the video's path in the compilations bucket.

**Deduplication** — At ingestion time, each photo's `google_photos_id` is checked against the Photo Index before writing. Photos already present are skipped. Prevents duplicate entries when re-ingesting overlapping Takeout Archives.

**Preview Image** — Single WebP file at 1280px wide (aspect ratio preserved), ~85% quality, ~150KB average. Generated at ingestion time. Used for both timeline grid and lightbox view.

## Deployment

- GCP Project: `photolib-405112` (existing)
- Infrastructure: Terraform in `infra/` directory
- Region: `us-central1` for all resources (Cloud Run, GCS, Firestore)
- App: Single Next.js container on Cloud Run Service (API routes + React frontend, one deployment unit)
- Ingestion: Cloud Run Job triggered manually via "Start Ingestion" button in the UI (API route calls GCP Jobs API)
- Ingestion status: UI polls Cloud Run Job execution status (running/succeeded/failed) every 10 seconds
- Auth (Drive/GCS): Single service account with Google Drive API and GCS access
- Auth (App access): Cloud Identity-Aware Proxy (IAP) in front of Cloud Run — only whitelisted Google account can access the UI
