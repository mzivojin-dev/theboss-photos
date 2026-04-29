# Require IAP for the Cloud Run service — deny all unauthenticated access
resource "google_cloud_run_v2_service_iam_binding" "deny_unauthenticated" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"

  # Only IAP service account may invoke Cloud Run directly
  members = [
    "serviceAccount:service-${data.google_project.project.number}@gcp-sa-iap.iam.gserviceaccount.com",
  ]
}

data "google_project" "project" {
  project_id = var.project_id
}

# Grant the authorized user access through IAP
resource "google_iap_web_iam_member" "authorized_user" {
  project = var.project_id
  role    = "roles/iap.httpsResourceAccessor"
  member  = "user:${var.iap_authorized_email}"
}
