resource "google_cloud_run_v2_service" "app" {
  name     = "theboss-photos"
  location = var.region
  labels   = local.cost_labels

  template {
    labels          = local.cost_labels
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
      env {
        name  = "INGEST_TRIGGER_MODE"
        value = "cloud"
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
  labels   = local.cost_labels

  template {
    labels = local.cost_labels

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
        env {
          name  = "STAGING_BUCKET"
          value = google_storage_bucket.staging.name
        }
        env {
          name  = "COMPILE_JOB_NAME"
          value = google_cloud_run_v2_job.compile.name
        }
        env {
          name  = "GCP_REGION"
          value = var.region
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

# Makes a Compilation (trip video) per changed trip. Started by the ingestion job after a run that
# indexed new media. Rendering 10-bit HEVC is CPU-bound, and the job's disk is in memory: a trip's
# clips, rendered segments and output all sit there at once.
resource "google_cloud_run_v2_job" "compile" {
  name     = "theboss-photos-compile"
  location = var.region
  labels   = local.cost_labels

  template {
    labels = local.cost_labels

    template {
      service_account = google_service_account.app.email
      timeout         = "21600s" # 6 hours
      max_retries     = 1

      containers {
        image = "gcr.io/${var.project_id}/theboss-photos-compile:latest"

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "STAGING_BUCKET"
          value = google_storage_bucket.staging.name
        }
        env {
          name  = "ORIGINALS_BUCKET"
          value = google_storage_bucket.originals.name
        }
        env {
          name  = "PREVIEWS_BUCKET"
          value = google_storage_bucket.previews.name
        }
        env {
          name  = "COMPILATIONS_BUCKET"
          value = google_storage_bucket.compilations.name
        }

        resources {
          limits = {
            cpu    = "8"
            memory = "16Gi"
          }
        }
      }
    }
  }
}
