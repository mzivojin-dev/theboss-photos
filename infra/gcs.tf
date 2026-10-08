resource "google_storage_bucket" "previews" {
  name                        = "${var.project_id}-previews"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.cost_labels

  lifecycle_rule {
    condition { age = 0 }
    action { type = "AbortIncompleteMultipartUpload" }
  }
}

resource "google_storage_bucket" "originals" {
  name                        = "${var.project_id}-originals"
  location                    = var.region
  storage_class               = "ARCHIVE"
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.cost_labels
}

# Staging: the Ingestion Job copies each newly indexed video (and a 1920px JPEG of each photo) here
# while it has the bytes, so the Compilation Job reads Standard storage instead of Archive.
# Copies are deleted after 30 days; a later re-render falls back to Originals and Previews.
resource "google_storage_bucket" "staging" {
  name                        = "${var.project_id}-staging"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.cost_labels

  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" }
  }

  lifecycle_rule {
    condition { age = 0 }
    action { type = "AbortIncompleteMultipartUpload" }
  }
}

# Compilations: one trip video per trip, written by the Compilation Job, served by signed URLs.
resource "google_storage_bucket" "compilations" {
  name                        = "${var.project_id}-compilations"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.cost_labels

  lifecycle_rule {
    condition { age = 0 }
    action { type = "AbortIncompleteMultipartUpload" }
  }
}
