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

output "billing_export_dataset_id" {
  value       = google_bigquery_dataset.billing_export.dataset_id
  description = "BigQuery dataset to select when enabling Cloud Billing detailed export."
}

output "monthly_budget_name" {
  value       = try(google_billing_budget.project_monthly[0].name, null)
  description = "Project-scoped monthly budget, or null when billing_account_id is unset."
}
