output "previews_bucket" {
  value = google_storage_bucket.previews.name
}

output "originals_bucket" {
  value = google_storage_bucket.originals.name
}

output "app_service_url" {
  value = google_cloud_run_v2_service.app.uri
}

output "service_account_email" {
  value = google_service_account.app.email
}

output "ingest_job_name" {
  value = google_cloud_run_v2_job.ingest.name
}
