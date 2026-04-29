# PRD-001: Google Takeout Photo Viewer

## Problem Statement

I have years of personal photos stored in Google Photos. Maintaining an active Google Photos subscription just to view my own photo archive is costly and creates dependency on a third-party service. Google Takeout allows exporting all photos as ZIP archives, but once exported, there is no good way to browse them — the raw ZIP files are unviewable without extracting everything manually. I need a self-hosted viewer that replicates the Google Photos browsing experience at minimal ongoing cost.

## Solution

A personal web application that ingests Google Takeout ZIP archives from Google Drive, processes them into a cost-optimised two-tier storage structure on Google Cloud Storage, and presents a chronological photo timeline with a lightbox viewer and on-demand original download — all hosted on GCP Cloud Run and accessible only to the owner.

## User Stories

1. As the owner, I want to drop Takeout Archive ZIP files into a Google Drive folder and trigger processing from the app, so that my photos are available to browse without manual extraction.
2. As the owner, I want the app to read ZIP files directly from Drive without downloading them fully, so that ingestion is fast and does not require large local or cloud disk.
3. As the owner, I want each photo's Preview Image generated automatically at ingestion time, so that browsing is fast without loading full-resolution files.
4. As the owner, I want Preview Images stored in GCS Standard tier, so that they load quickly every time I browse.
5. As the owner, I want Original photos stored in GCS Archive tier as individual files, so that long-term storage cost is minimised.
6. As the owner, I want Takeout Archive ZIPs discarded after ingestion, so that I am not paying to store them twice.
7. As the owner, I want duplicate photos detected and skipped automatically when re-ingesting overlapping Takeout Archives, so that the same photo does not appear multiple times in the timeline.
8. As the owner, I want to see a chronological timeline of all my photos scrolling from most recent to oldest, so that I can browse my photo history naturally.
9. As the owner, I want the timeline to load the next batch of photos automatically as I scroll down, so that browsing feels seamless without clicking through pages.
10. As the owner, I want to click a photo in the timeline to open a full-screen lightbox view, so that I can see the photo clearly.
11. As the owner, I want to navigate to the previous and next photo from within the lightbox, so that I can browse sequentially without returning to the grid.
12. As the owner, I want a download button in the lightbox that retrieves the full-resolution Original, so that I can access the highest quality version when needed.
13. As the owner, I want the ingestion to be triggered by a button in the app, so that I have explicit control over when processing runs.
14. As the owner, I want to see a live status indicator (Running / Done / Failed) while ingestion is in progress, so that I know the job has started and when it finishes.
15. As the owner, I want the app protected by Google Identity-Aware Proxy, so that only my Google account can access it — no password management required.
16. As the owner, I want the entire infrastructure defined in Terraform, so that I can recreate or tear down the stack reliably.
17. As the owner, I want all GCP resources in us-central1, so that costs are minimised and services are co-located.
18. As the owner, I want Preview Images served via short-lived signed GCS URLs, so that the previews bucket stays private and URLs cannot be shared indefinitely.
19. As the owner, I want the photo metadata (date, paths, dimensions) stored in Firestore, so that timeline queries are fast without scanning GCS.
20. As the owner, I want the app to run as a single container on Cloud Run, so that there is no always-on infrastructure cost when I am not browsing.

## Implementation Decisions

### Modules

**1. Terraform Infrastructure (`infra/`)**
Provisions all GCP resources: two GCS buckets (Standard for previews, Archive for originals), Firestore database in Native mode, service account with Drive API and GCS IAM bindings, Cloud Run service and job resource definitions, and IAP OAuth configuration. This is the foundation — all other modules depend on it.

**2. Drive ZIP Streamer**
A deep module that authenticates with Google Drive API using a service account, reads the ZIP central directory via a Range request (last bytes of the file), then exposes an iterator over ZIP entries where each entry's compressed bytes are fetched individually via a second Range request. Interface: `list_zip_entries(file_id) -> Iterator[ZipEntry]`. No full ZIP download ever occurs. This module can be tested in isolation with a mock Drive HTTP client.

**3. Image Processor**
A deep module that accepts raw image bytes (JPEG, HEIC, PNG) and returns a resized WebP byte payload. Resize target: 1280px wide, aspect ratio preserved, 85% quality. Interface: `process(raw_bytes: bytes) -> webp_bytes: bytes`. Stateless and side-effect-free — easy to unit test.

**4. Sidecar Parser**
Parses a Takeout `.json` sidecar file and extracts: `taken_at` (timestamp), `google_photos_id` (from the `url` field — stable unique identifier), and any available GPS coordinates. Interface: `parse(json_bytes: bytes) -> PhotoMetadata`. Stateless.

**5. Photo Index Repository**
Wraps Firestore. Interface: `exists(google_photos_id) -> bool` for dedup check, `upsert(photo_doc)` to write a new Photo Index entry. A Photo Index document contains: `taken_at`, `preview_gcs_path`, `original_gcs_path`, `filename`, `width`, `height`, `google_photos_id`.

**6. Ingestion Job (`jobs/ingest/`)**
Cloud Run Job container. Orchestrates the pipeline: for each Takeout Archive ZIP in the Drive Folder → iterate entries via Drive ZIP Streamer → for each image entry, check dedup via Photo Index Repository → decompress → run Image Processor → upload Preview to Standard GCS + Original to Archive GCS → parse paired Sidecar → write to Photo Index Repository. Runs to completion and exits.

**7. Next.js App (`app/`)**
Single container on Cloud Run Service. Contains:
- API route `POST /api/ingest/trigger` — calls GCP Cloud Run Jobs API to start the Ingestion Job
- API route `GET /api/ingest/status` — polls the latest Cloud Run Job execution for status (RUNNING / SUCCEEDED / FAILED)
- API route `GET /api/photos` — queries Firestore ordered by `taken_at` desc, accepts a cursor parameter, returns 50 photos per page each with a freshly-generated signed Preview URL (1hr TTL)
- API route `GET /api/photos/[id]/download` — generates a signed Archive GCS URL for the Original and redirects the browser to it
- React Timeline component — masonry/grid layout, fetches first batch on mount, triggers next batch fetch on scroll-to-bottom
- React Lightbox component — full-screen overlay, previous/next navigation, download button
- React Ingestion Panel — trigger button, polls `/api/ingest/status` every 10 seconds, shows status badge

### API Contracts

**GET /api/photos**
- Query params: `cursor` (optional Firestore document ID), `limit` (default 50)
- Response: `{ photos: [{ id, taken_at, preview_url, width, height }], next_cursor }`

**GET /api/photos/[id]/download**
- Response: HTTP 302 redirect to signed Archive GCS URL (1hr TTL)

**POST /api/ingest/trigger**
- Response: `{ execution_name: string }`

**GET /api/ingest/status**
- Response: `{ status: "RUNNING" | "SUCCEEDED" | "FAILED" | "IDLE", started_at, completed_at }`

### Architectural Decisions

- **No full ZIP download**: Drive API byte-range requests only. ZIP central directory read once; each file fetched by offset. Avoids disk/memory pressure on Cloud Run.
- **Dedup by `google_photos_id`**: Derived from the sidecar `url` field. Stable across re-exports. No content hashing required.
- **Single preview size**: 1280px wide WebP. Serves both grid thumbnails (browser scales down) and lightbox. Simplifies ingestion; one GCS object per photo.
- **Signed URLs, not public bucket**: Previews bucket is private. API route generates signed URLs per request. IAP ensures only the owner can call the API.
- **Firestore, not Cloud SQL**: No always-on cost. Free tier covers personal-scale reads/writes. Single collection with composite index on `taken_at`.

## Testing Decisions

Good tests in this codebase test external observable behaviour, not internal implementation. They do not assert on private methods, intermediate variables, or specific function call sequences — only on inputs and outputs.

**Drive ZIP Streamer** — unit tested with a mock HTTP client returning pre-built ZIP byte fixtures. Assert that the correct Range request headers are sent and that the iterator yields the expected entries with correct bytes.

**Image Processor** — unit tested with a set of fixture images (JPEG, HEIC, PNG). Assert that output is valid WebP, output width is 1280px, aspect ratio is preserved within 1px, file size is below a threshold.

**Sidecar Parser** — unit tested with fixture JSON files from real Takeout exports. Assert that `taken_at`, `google_photos_id`, and GPS fields are correctly extracted. Assert graceful handling of missing fields.

**Photo Index Repository** — integration tested against the Firestore emulator. Assert that `exists()` returns false for unknown IDs and true after `upsert()`. Assert that a second `upsert()` with the same `google_photos_id` does not create a duplicate document.

**API routes** — integration tested with a running Next.js test server and mocked GCP clients. Assert correct HTTP status codes, response shapes, and that signed URL generation is called with the correct GCS paths.

## Out of Scope

- Albums view
- Map view (photos by GPS location)
- Search (by date range, filename, or metadata)
- Face or object recognition / AI tagging
- Video playback
- Shared access (share a link with another person)
- Automatic ingestion trigger (Drive webhook or Cloud Scheduler)
- Multi-user support

## Further Notes

- The Drive Folder ID must be configured as an environment variable on the Ingestion Job. The user places Takeout Archives in this folder manually before triggering ingestion.
- GCS Archive storage class enforces a 365-day minimum storage duration. Early deletion incurs a pro-rated charge. This is acceptable for permanent personal photo storage.
- Cloud Run Job timeout is set to 168 hours (maximum). A 10GB Takeout Archive processing ~25,000 photos with image resizing should complete well within 1–2 hours in practice.
- Estimated monthly cost for 100GB of originals: ~$0.37/month (Archive storage + Standard preview storage + GCS egress). Scales linearly.
- The Next.js container should set `NEXT_PUBLIC_` env vars for any config needed client-side. GCP credentials must never be exposed to the client bundle.
