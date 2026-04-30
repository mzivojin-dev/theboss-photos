resource "google_firestore_database" "main" {
  project     = var.project_id
  name        = "photo-lib"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

