resource "google_service_account" "app" {
  account_id   = "theboss-photos-app"
  display_name = "theboss-photos app + ingestion service account"
}

# GCS: read/write previews bucket
resource "google_storage_bucket_iam_member" "app_previews_rw" {
  bucket = google_storage_bucket.previews.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app.email}"
}

# GCS: read/write originals bucket
resource "google_storage_bucket_iam_member" "app_originals_rw" {
  bucket = google_storage_bucket.originals.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app.email}"
}

# Firestore: read/write
resource "google_project_iam_member" "app_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# Cloud Run Jobs: invoke (so the Next.js API route can trigger the ingestion job)
resource "google_project_iam_member" "app_run_jobs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# Allow the service account to act as itself (for signing GCS URLs)
resource "google_service_account_iam_member" "app_token_creator" {
  service_account_id = google_service_account.app.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.app.email}"
}
