resource "google_firestore_database" "main" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

resource "google_firestore_index" "photos_by_taken_at" {
  project    = var.project_id
  database   = google_firestore_database.main.name
  collection = "photos"

  fields {
    field_path = "taken_at"
    order      = "DESCENDING"
  }

  fields {
    field_path = "__name__"
    order      = "DESCENDING"
  }
}
