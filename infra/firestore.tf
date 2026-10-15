resource "google_firestore_database" "main" {
  project     = var.project_id
  name        = "photo-lib"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

# Nearest-neighbour search over the photos' embeddings (semantic search, /api/search). The dimension
# matches DIMENSIONS in jobs/compile/src/photo_embeddings.py; a new model with another dimension
# needs a new index. Flat is the only index type Firestore offers.
resource "google_firestore_index" "photos_embedding" {
  project    = var.project_id
  database   = google_firestore_database.main.name
  collection = "photos"

  fields {
    field_path = "__name__"
    order      = "ASCENDING"
  }

  fields {
    field_path = "embedding"
    vector_config {
      dimension = 768
      flat {}
    }
  }
}
