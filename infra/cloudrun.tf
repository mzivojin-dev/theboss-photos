resource "google_cloud_run_v2_service" "app" {
  name     = "theboss-photos"
  location = var.region
  labels   = local.cost_labels
  # Cloud Run's built-in IAP: only the account in iap.tf gets in. Without it, requests reach Cloud
  # Run unauthenticated and get "403 Forbidden", since only the IAP service agent may invoke it.
  iap_enabled  = true
  launch_stage = "BETA"

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
      env {
        name  = "EMBED_SERVICE_URL"
        value = google_cloud_run_v2_service.embed_text.uri
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
        # The service account can't delete ZIPs you own in a My Drive folder; clear the folder by hand.
        env {
          name  = "DELETE_PROCESSED_DRIVE_FILES"
          value = "false"
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
          name  = "GROUP_JOB_NAME"
          value = google_cloud_run_v2_job.group.name
        }
        env {
          name  = "EMBED_JOB_NAME"
          value = google_cloud_run_v2_job.embed.name
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

# Groups similar photos behind a cover (see "Similar Group" in CONTEXT.md). Runs from the compile
# image, which has the face detector. Started by the ingestion job after a run that indexed new
# media; measures only photos it hasn't yet, so reruns are cheap.
resource "google_cloud_run_v2_job" "group" {
  name     = "theboss-photos-group"
  location = var.region
  labels   = local.cost_labels

  template {
    labels = local.cost_labels

    template {
      service_account = google_service_account.app.email
      timeout         = "3600s"
      max_retries     = 1

      containers {
        image   = "gcr.io/${var.project_id}/theboss-photos-compile:latest"
        command = ["python", "-m", "src.group_main"]

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "PREVIEWS_BUCKET"
          value = google_storage_bucket.previews.name
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

# Embeds photos for semantic search (see "Embedding Job" in CONTEXT.md). Runs from the compile image,
# which has the model weights baked in. Started by the ingestion job after a run that indexed new
# media; embeds only photos without a vector from the current model, so reruns are cheap.
resource "google_cloud_run_v2_job" "embed" {
  name     = "theboss-photos-embed"
  location = var.region
  labels   = local.cost_labels

  template {
    labels = local.cost_labels

    template {
      service_account = google_service_account.app.email
      timeout         = "21600s" # 6 hours: a first run embeds the whole library at ~0.2s a photo
      max_retries     = 1

      containers {
        image   = "gcr.io/${var.project_id}/theboss-photos-compile:latest"
        command = ["python", "-m", "src.embed_main"]

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "PREVIEWS_BUCKET"
          value = google_storage_bucket.previews.name
        }

        resources {
          limits = {
            cpu    = "4"
            memory = "4Gi"
          }
        }
      }
    }
  }
}

# Embeds search text with the same model, for the app's /api/search. Private: only the app's
# service account may invoke it (iam.tf). Scales to zero, so the first search after a quiet spell
# waits for the model to load (~20s).
resource "google_cloud_run_v2_service" "embed_text" {
  name     = "theboss-photos-embed-text"
  location = var.region
  labels   = local.cost_labels

  template {
    labels          = local.cost_labels
    service_account = google_service_account.app.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image   = "gcr.io/${var.project_id}/theboss-photos-compile:latest"
      command = ["python", "-m", "src.embed_server"]

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      startup_probe {
        tcp_socket {
          port = 8080
        }
        period_seconds    = 5
        failure_threshold = 24 # two minutes for the model to load
      }
    }
  }
}
