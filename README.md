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
        ├── Staged copy (new media)     ──► GCS Standard (30 days) ─┐
        └── Metadata                    ──► Firestore     ◄── timeline queries
        │                                                            │
        ▼  (jobs.run, after a run that indexed new media)            ▼
   Compilation Job (Cloud Run Job, Python + ffmpeg)  ── reads staged media, the Photo Index
        └── Compilation (trip video)    ──► GCS Standard  + `compilations` in Firestore
   Grouping Job (Cloud Run Job, Python + OpenCV)     ── reads Previews, the Photo Index
        └── Similar Groups              ──► `grouped_under` / `group_size` in Firestore
```

**App** — Next.js on Cloud Run, behind Cloud IAP (single Google account only). Infinite-scroll timeline in day sections, with each group of similar photos shown as one cover tile with a "+N" badge; a lightbox with prev/next, a strip of the similar photos behind a cover (arrow up/down steps through it) and "Use as cover"; on-demand original download; ingestion trigger + status polling.

**Ingestion Job** — Cloud Run Job. For each ZIP in the Drive folder: streams the ZIP central directory via Range requests, extracts each photo/video in-memory, generates a 1280px WebP preview, writes to GCS, indexes metadata to Firestore, and logs whether the ZIP was fully ingested (you then delete it from Drive). Deduplicates by `google_photos_id` so re-ingesting overlapping archives is safe.

**Compilation Job** — Cloud Run Job, started by the Ingestion Job after a run that indexed new media. Finds Trips (runs of days more than 50 km from home, with video) and makes a Compilation for each Trip whose media changed: the best stretch of each clip, photos preferring clear faces, a chapter per day, captions, and public-domain music. Output keeps the footage's orientation and HDR. See [ADR 0001](docs/adr/0001-compilations-via-staging-and-a-job-started-by-ingestion.md).

**Grouping Job** — Cloud Run Job (`theboss-photos-group`, run from the compile image), started by the Ingestion Job alongside the Compilation Job. Groups similar photos (bursts, retakes) behind a cover: every pair has perceptual hashes within 10 of 64 bits and the same number of clear faces, and the group spans at most 2 minutes. It measures only photos it hasn't yet, regroups all of them, and writes `grouped_under` (on the photos behind a cover), `group_size` (on the cover) and `cover_pinned` (a cover you chose) to the Photo Index. **Every file is kept; nothing is deleted.** Safe to repeat. See *Similar Group* in [CONTEXT.md](CONTEXT.md).

## Prerequisites

- GCP project with billing enabled
- Terraform 1.6+
- `gcloud` CLI
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

This provisions: four GCS buckets (Standard for previews, staging and compilations; Archive for originals), Firestore database `photo-lib`, the Cloud Run service, the ingestion, compilation and grouping jobs, the service account, and IAP.

### Cost attribution and analysis

Terraform applies consistent `application`, `environment`, `cost_center`, and `managed_by` labels to the photo buckets, Cloud Run service and revisions, Cloud Run job, and the BigQuery export dataset. These labels make resource-level billing rows easier to group and explain. Firestore database labels are not supported by the configured Google provider API, so its spend remains attributable by project and service rather than these labels. Set `environment` and `cost_center` to match your organization's allocation vocabulary.

Terraform also creates a US multi-region BigQuery dataset named `<project-id-with-hyphens-replaced-by-underscores>_billing_export`. Dataset creation does **not** start the billing export: a billing-account administrator must enable **Detailed usage cost** (and, optionally, **Pricing**) export in **Billing → Billing export → BigQuery export**, selecting the project and dataset shown by:

```bash
terraform output billing_export_dataset_id
```

The export is configured at the billing-account level, not by this project's Terraform provider; it requires billing-account permissions and produces data after export is enabled. Terraform enables BigQuery and BigQuery Data Transfer APIs for the project; a billing-account administrator still needs to select the export types and dataset in the console. Detailed usage cost export is recommended for resource-level attribution. Pricing export helps explain unit rates. BigQuery storage and queries can incur charges, so use partition filters and avoid repeatedly scanning the full export tables.

After export starts, a simple monthly breakdown can be built from the detailed resource export table (replace the project, dataset, and billing account ID with the values shown in BigQuery):

```sql
SELECT
  invoice.month,
  service.description AS service,
  sku.description AS sku,
  project.id AS project_id,
  (SELECT STRING_AGG(CONCAT(label.key, "=", label.value), ", ")
   FROM UNNEST(labels) AS label) AS resource_labels,
  SUM(cost) AS gross_cost,
  SUM(IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit), 0)) AS credits,
  SUM(cost + IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit), 0)) AS net_cost
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID`
WHERE invoice.month >= FORMAT_DATE("%Y%m", DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH))
GROUP BY invoice.month, service, sku, project_id, resource_labels
ORDER BY invoice.month DESC, net_cost DESC;
```

To also create a monthly, project-scoped budget and email notifications, supply the billing account ID and alert address during `terraform apply`:

```bash
terraform apply \
  -var="iap_authorized_email=you@gmail.com" \
  -var="drive_folder_id=<your-drive-folder-id>" \
  -var="billing_account_id=000000-000000-000000" \
  -var="monthly_budget_amount=50" \
  -var="budget_currency=USD" \
  -var="cost_alert_email=you@example.com"
```

The budget notifies at 50%, 80%, 100%, and 100% forecasted spend. `monthly_budget_amount` is in whole currency units and must use the billing account's currency. If `cost_alert_email` is omitted, notifications go to billing IAM recipients and project-level recipients. Budgets are alerts, **not spending caps**, and billing data/alerts can be delayed. Leave `billing_account_id` unset to skip budget creation.

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

**Compilation job:**
```bash
cd jobs/compile
docker build -t gcr.io/photolib-405112/theboss-photos-compile:latest .
docker push gcr.io/photolib-405112/theboss-photos-compile:latest
```

The compilation image must be pushed before the first `terraform apply` that creates the jobs, or Cloud Run rejects them. The photo grouping job (`theboss-photos-group`) runs from this same image.

### 3. Deploy

```bash
cd infra && terraform apply   -var="iap_authorized_email=you@gmail.com"   -var="drive_folder_id=<your-drive-folder-id>"
```

The app URL is printed as a Terraform output. IAP will prompt for your Google account on first access.

Every image uses the `:latest` tag, so `terraform apply` does **not** roll out a rebuilt image (the configuration doesn't change). After pushing new images, point the service and jobs at them:

```bash
R="--region us-central1 --project photolib-405112"
gcloud run services update theboss-photos $R --image gcr.io/photolib-405112/theboss-photos@sha256:<digest>
gcloud run jobs update theboss-photos-ingest $R --image gcr.io/photolib-405112/theboss-photos-ingest@sha256:<digest>
gcloud run jobs update theboss-photos-compile $R --image gcr.io/photolib-405112/theboss-photos-compile@sha256:<digest>
gcloud run jobs update theboss-photos-group $R --image gcr.io/photolib-405112/theboss-photos-compile@sha256:<digest>
```

Each `docker push` prints its digest. Terraform state is in the `photolib-405112-tfstate` bucket; run Terraform as your own Google account, since the app service account can't read it. To group an existing library the first time (or after changing the grouping rules), run `gcloud run jobs execute theboss-photos-group --region us-central1`.

## Usage

1. **Export your photos** from [Google Takeout](https://takeout.google.com). Choose Google Photos, ZIP format.
2. **Upload the ZIP files** to the Google Drive folder whose ID you passed to Terraform.
3. **Open the app** and click **Start Ingestion**. A status badge shows Running → Done / Failed.
4. **Browse** the timeline. Scroll to load more; photos are grouped by day, and similar photos show as one cover with a "+N" badge. Click a photo for the lightbox; on a cover, pick any of the similar photos in the strip and click **Use as cover** to change which one the timeline shows. Use the download button to retrieve the full-resolution original.

Ingestion also keeps an **Ingestion Ledger** in Firestore (`takeout_problems`, `takeout_exports`): every file it could not index, and which `Photos from YYYY` years each Takeout export contained. Archives ingested before the ledger existed have no entries; re-run ingestion over their ZIPs to fill it in (indexed files are skipped, so it is cheap). See [ADR 0002](docs/adr/0002-google-photos-deletion-is-manual.md).

Ingestion is safe to re-run — already-indexed photos are skipped. Processed ZIPs stay in Drive: the service account can't delete files you own in a My Drive folder, so delete them yourself once the archive summary in the job logs says `fully ingested` (an archive that is `kept` still has files without a Sidecar, usually because another part of the export is missing).

## Development

### Run with Docker Compose on Windows

The Compose setup runs the Next.js app locally while connecting to the configured Google Cloud project. It does not emulate GCS, Firestore, or Cloud Run.

1. Copy `.env.example` to `.env` and set the project, bucket, region, and Drive folder values for your deployment:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
2. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) if needed. The app signs Google Cloud Storage URLs, so local credentials must impersonate the app service account. Ask a project administrator to grant your Google account `roles/iam.serviceAccountTokenCreator` on `theboss-photos-app@<project-id>.iam.gserviceaccount.com`, replacing the project ID with the value in `.env`. Then create impersonated Application Default Credentials:

   ```powershell
   gcloud auth application-default login --impersonate-service-account=theboss-photos-app@<project-id>.iam.gserviceaccount.com --scopes=https://www.googleapis.com/auth/cloud-platform
   ```

   Replace `<project-id>` with the project ID from `.env`. Verify that `%APPDATA%\gcloud\application_default_credentials.json` exists as a file (not a directory). If Docker previously created an empty directory at that exact path because the credentials file was missing, remove that empty directory before running the login command. The Compose services mount the resulting credentials file read-only and will fail to start if it is missing. Plain user ADC without service-account impersonation can access Google APIs but cannot sign the app's storage URLs.
3. Start Docker Desktop, then run `build.bat` from the repository root. Alternatively, run `docker compose build app ingest` (and `docker compose --profile compile build compile` for the Compilation Job).
4. Start the app with `docker compose up -d` and open <http://localhost:3000>. View logs with `docker compose logs -f app`; stop it with `docker compose down`.

Compose starts both the web app and a private local ingestion service. Its **Start Ingestion** button runs ingestion in that service; the ingestion container stays available and runs a job only when triggered. In Cloud Run, Terraform sets the trigger mode to `cloud`, so the same button starts the configured Cloud Run Job instead.

```powershell
gcloud auth application-default login --impersonate-service-account=theboss-photos-app@<project-id>.iam.gserviceaccount.com --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive
```

For local Docker ingestion, ADC needs both the Cloud Platform and Drive scopes, and the impersonated service account must be able to read the Drive folder and files. Local Compose leaves processed ZIPs in Drive by default, so it does not need delete permission. You can enable deletion by setting `DELETE_PROCESSED_DRIVE_FILES=true` on the `ingest` service in `compose.yaml`; the service account must then have permission to delete the files (Shared Drive files may require the Content manager role).

**Cleanup page with sample data:** `docker compose --profile demo up --build app-demo`, then open http://localhost:3001/cleanup. It uses `CLEANUP_FAKE_DATA=true`: an in-memory store with sample photos, an export, problems and a bucket listing, and needs no Google credentials. Marking a range deleted works (including the audit history) but is forgotten when the container stops.

**Similar photos locally:** `docker compose run --rm group` groups similar photos in the real Photo Index (needs `GCP_PROJECT_ID` and `PREVIEWS_BUCKET`). It writes grouping fields only; no file is deleted. Leave `GROUP_JOB_NAME` empty locally unless local ingestion should start the job in Cloud Run.

**Compilations locally:** set `STAGING_BUCKET` in `.env` to stage new media during local ingestion, and `COMPILATIONS_BUCKET` to run the Compilation Job with `docker compose run --rm compile`. It reads the real Photo Index and buckets, and writes real Compilations. Leave `COMPILE_JOB_NAME` empty locally unless local ingestion should start the job in Cloud Run.

**Run Python tests:**
```bash
cd jobs/ingest
python -m pytest
cd ../compile
python -m pip install -r requirements-dev.txt   # tzdata gives Windows a time zone database
python -m pytest
```

**Debug ingestion locally on Windows:**

Install the ingestion development requirements into the Python environment you use in VS Code:

```powershell
cd jobs/ingest
python -m pip install -r requirements-dev.txt
```

Set `DRIVE_FOLDER_ID` and the GCP project/bucket values in the repository-root `.env`. Create Application Default Credentials with the Cloud Platform and Drive scopes, then run `jobs\ingest\debug.bat` from a terminal using that Python environment. The batch file loads the root `.env`, checks the ADC file, and starts `src.main` as a package, paused until a debugger attaches to `127.0.0.1:5678`. In VS Code, set breakpoints in `jobs/ingest/src`, run **Attach to ingestion (debug.bat)** from the Run and Debug panel, and then start `debug.bat` in the terminal (or start the batch first). Do not use **Run Python File** or F5 while `main.py` is selected: that launches it outside its package and causes relative-import errors. The debug run processes the configured Drive folder, so it can upload objects and update Firestore; local Compose is configured not to delete source ZIPs.

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

For local development without Docker, set the following environment variables in `app/.env.local` and use the same service-account-impersonated ADC described above:
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
jobs/compile/   Python Compilation Job and Grouping Job + pytest tests
app/            Next.js app (API routes + React frontend)
docs/
  prd-001-google-photos-viewer.md   Full product spec
  adr/                              Architecture decision records
  agents/                           Agent skill configuration
CONTEXT.md      Domain glossary
```

## Cost estimate

~$0.37/month per 100GB of originals (GCS Archive + Standard storage + egress). Cloud Run scales to zero — no idle cost.
