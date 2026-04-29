resource "google_cloud_run_v2_service" "app" {
  name     = "theboss-photos"
  location = var.region

  template {
    service_account = google_service_account.app.email

    containers {
      image = "gcr.io/${var.project_id}/theboss-photos:latest"

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "PREVIEWS_BUCKET"
        value = google_storage_bucket.previews.name
      }
      env {
        name  = "ORIGINALS_BUCKET"
        value = google_storage_bucket.originals.name
      }
      env {
        name  = "INGEST_JOB_NAME"
        value = google_cloud_run_v2_job.ingest.name
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "ingest" {
  name     = "theboss-photos-ingest"
  location = var.region

  template {
    template {
      service_account = google_service_account.app.email
      timeout         = "86400s" # 24 hours

      containers {
        image = "gcr.io/${var.project_id}/theboss-photos-ingest:latest"

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "PREVIEWS_BUCKET"
          value = google_storage_bucket.previews.name
        }
        env {
          name  = "ORIGINALS_BUCKET"
          value = google_storage_bucket.originals.name
        }
        env {
          name  = "DRIVE_FOLDER_ID"
          value = var.drive_folder_id
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }
    }
  }
}
