# theboss-photos

A self-hosted Google Takeout photo viewer. Drop Takeout ZIP archives into a Google Drive folder, trigger ingestion from the app, and browse a chronological photo timeline — all on GCP, accessible only to you.

## How it works

```
Google Drive folder
  └── Takeout_001.zip
  └── Takeout_002.zip
        │
        ▼  (byte-range streams — no full download)
   Ingestion Job (Cloud Run Job, Python)
        │
        ├── Preview Image (1280px WebP) ──► GCS Standard  ◄── Next.js app (signed URLs)
        ├── Original (full-res)         ──► GCS Archive   ◄── on-demand download
        └── Metadata                    ──► Firestore     ◄── timeline queries
```

**App** — Next.js on Cloud Run, behind Cloud IAP (single Google account only). Infinite-scroll timeline, lightbox with prev/next, on-demand original download, ingestion trigger + status polling.

**Ingestion Job** — Cloud Run Job. For each ZIP in the Drive folder: streams the ZIP central directory via Range requests, extracts each photo/video in-memory, generates a 1280px WebP preview, writes to GCS, indexes metadata to Firestore, then deletes the ZIP from Drive. Deduplicates by `google_photos_id` so re-ingesting overlapping archives is safe.

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth login`)
- Terraform ≥ 1.5
- Docker (for building container images)
- Node.js 20+ and Python 3.11+

## Setup

### 1. Terraform

```bash
cd infra
terraform init
terraform apply \
  -var="iap_authorized_email=you@gmail.com" \
  -var="drive_folder_id=<your-drive-folder-id>"
```

This provisions: two GCS buckets (Standard for previews, Archive for originals), Firestore database `photo-lib`, Cloud Run service + job, service account, and IAP.

### 2. Build and push container images

**App:**
```bash
cd app
docker build -t gcr.io/photolib-405112/theboss-photos:latest .
docker push gcr.io/photolib-405112/theboss-photos:latest
```

**Ingestion job:**
```bash
cd jobs/ingest
docker build -t gcr.io/photolib-405112/theboss-photos-ingest:latest .
docker push gcr.io/photolib-405112/theboss-photos-ingest:latest
```

### 3. Deploy

```bash
# Re-apply Terraform to pick up the new images
cd infra && terraform apply \
  -var="iap_authorized_email=you@gmail.com" \
  -var="drive_folder_id=<your-drive-folder-id>"
```

The app URL is printed as a Terraform output. IAP will prompt for your Google account on first access.

## Usage

1. **Export your photos** from [Google Takeout](https://takeout.google.com). Choose Google Photos, ZIP format.
2. **Upload the ZIP files** to the Google Drive folder whose ID you passed to Terraform.
3. **Open the app** and click **Start Ingestion**. A status badge shows Running → Done / Failed.
4. **Browse** the timeline. Scroll to load more. Click a photo for the lightbox. Use the download button to retrieve the full-resolution original.

Ingestion is safe to re-run — already-indexed photos are skipped. ZIPs are deleted from Drive after successful processing.

## Development

**Run Python tests:**
```bash
cd jobs/ingest
python -m pytest
```

**Run Next.js tests:**
```bash
cd app
npm test
```

**Next.js local dev:**
```bash
cd app
npm install
npm run dev
```

For local dev, set the following environment variables (`.env.local`):
```
GCP_PROJECT_ID=<project_id>
PREVIEWS_BUCKET=<previews-bucket-name>
ORIGINALS_BUCKET=<originals-bucket-name>
INGEST_JOB_NAME=theboss-photos-ingest
GCP_REGION=us-central1
```

## Project structure

```
infra/          Terraform — GCS, Firestore, Cloud Run, IAP, IAM
jobs/ingest/    Python ingestion job + pytest tests
app/            Next.js app (API routes + React frontend)
docs/
  prd-001-google-photos-viewer.md   Full product spec
  agents/                           Agent skill configuration
CONTEXT.md      Domain glossary
```

## Cost estimate

~$0.37/month per 100GB of originals (GCS Archive + Standard storage + egress). Cloud Run scales to zero — no idle cost.
