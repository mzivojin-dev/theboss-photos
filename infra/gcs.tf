resource "google_storage_bucket" "previews" {
  name                        = "${var.project_id}-previews"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

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
}
