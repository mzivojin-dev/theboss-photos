"""
Embeds photos for semantic search (see photo_embeddings.py). Run by hand or by the Ingestion Job:

    python -m src.embed_main

Needs GCP_PROJECT_ID and PREVIEWS_BUCKET (see .env.example). Nothing is deleted.
"""
import logging
import os
import sys

from google.cloud import firestore, storage
from google.cloud.exceptions import NotFound
from google.cloud.firestore_v1.vector import Vector

from .gcp import PHOTO_INDEX
from .group_main import GcsPreviews
from .photo_embeddings import MODEL_ID, IndexedPhoto, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


class FirestorePhotos:
    def __init__(self, db: firestore.Client):
        self._db = db
        self._collection = db.collection(PHOTO_INDEX)

    def photos(self) -> list[IndexedPhoto]:
        result = []
        for doc in self._collection.select(["media_type", "preview_gcs_path", "embedding_model"]).stream():
            data = doc.to_dict()
            if data.get("media_type", "photo") != "photo":
                continue
            result.append(IndexedPhoto(doc.id, data.get("preview_gcs_path"), data.get("embedding_model")))
        return result

    def save_embeddings(self, embeddings: dict[str, list[float]]) -> None:
        try:
            self._commit(embeddings)
        except NotFound:
            # A photo in the batch was removed since it was read: write the rest one by one.
            for photo_id, vector in embeddings.items():
                try:
                    self._commit({photo_id: vector})
                except NotFound:
                    log.warning("Photo %s no longer exists; skipped", photo_id)

    def _commit(self, embeddings: dict[str, list[float]]) -> None:
        batch = self._db.batch()
        for photo_id, vector in embeddings.items():
            batch.update(self._collection.document(photo_id), {
                "embedding": Vector(vector),
                "embedding_model": MODEL_ID,
                "embedded_at": firestore.SERVER_TIMESTAMP,
            })
        batch.commit()


def main() -> int:
    missing = [name for name in ("GCP_PROJECT_ID", "PREVIEWS_BUCKET") if not os.environ.get(name)]
    if missing:
        log.error("Set %s (see .env.example)", ", ".join(missing))
        return 2
    from .siglip import SiglipEmbedder  # loads torch; kept out of the module import for the tests

    project = os.environ["GCP_PROJECT_ID"]
    db = firestore.Client(project=project, database="photo-lib")
    previews = storage.Client(project=project).bucket(os.environ["PREVIEWS_BUCKET"])
    # Photos that can't be embedded are logged and skipped. They are not a failure: retrying the
    # whole job would not make a broken preview readable.
    run(FirestorePhotos(db), GcsPreviews(previews), SiglipEmbedder())
    return 0


if __name__ == "__main__":
    sys.exit(main())
