"""
Embeds each photo's Preview as a vector, so the library can be searched by meaning ("kids on a beach
at sunset"). Text queries are embedded by the same model (see embed_server.py) and matched against
these vectors with Firestore's nearest-neighbour search.

The Photo Index records this as `embedding` (the vector), `embedding_model` (MODEL_ID, the model
that made it) and `embedded_at`. A photo is embedded when it has no vector from the current model,
so changing MODEL_ID re-embeds everything on the next run. Every file is kept: this only adds fields.
"""
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Protocol

log = logging.getLogger(__name__)

MODEL_NAME = "ViT-B-16-SigLIP2"
PRETRAINED = "webli"
MODEL_ID = f"open_clip/{MODEL_NAME}/{PRETRAINED}"
DIMENSIONS = 768  # the vector index in infra/firestore.tf has the same dimension
BATCH_SIZE = 32


@dataclass
class IndexedPhoto:
    id: str
    preview_path: Optional[str]
    embedding_model: Optional[str]  # the model of the stored vector, if there is one


class PhotoStore(Protocol):
    def photos(self) -> list[IndexedPhoto]: ...

    def save_embeddings(self, embeddings: dict[str, list[float]]) -> None: ...


class PreviewSource(Protocol):
    def fetch(self, preview_path: str, directory: str) -> Optional[str]: ...


class Embedder(Protocol):
    def embed_images(self, paths: list[str]) -> list[Optional[list[float]]]:
        """One unit vector per path, or None for an image that can't be read."""
        ...


@dataclass(frozen=True)
class Summary:
    photos: int
    embedded: int
    skipped: int  # no Preview to fetch, or one the model couldn't read


def run(store: PhotoStore, previews: PreviewSource, embedder: Embedder, batch_size: int = BATCH_SIZE) -> Summary:
    """Embed every photo without a vector from MODEL_ID, a batch at a time.

    Safe to repeat and to overlap: a photo already embedded with MODEL_ID is left alone, and two runs
    embedding the same photo write the same vector. Each batch is saved as it is done, so a run that
    stops half way keeps what it did. A photo that can't be embedded is logged and skipped; the next
    run tries it again."""
    photos = store.photos()
    todo = [p for p in photos if p.embedding_model != MODEL_ID and p.preview_path]
    embedded = skipped = 0
    log.info("%d of %d photo(s) need embedding with %s", len(todo), len(photos), MODEL_ID)
    with tempfile.TemporaryDirectory() as directory:
        for start in range(0, len(todo), batch_size):
            fetched: list[tuple[IndexedPhoto, str]] = []
            for photo in todo[start:start + batch_size]:
                local = previews.fetch(photo.preview_path, directory)
                if local:
                    fetched.append((photo, local))
                else:
                    log.warning("Photo %s has no Preview at %s; skipped", photo.id, photo.preview_path)
                    skipped += 1
            vectors = embedder.embed_images([local for _, local in fetched]) if fetched else []
            batch = {}
            for (photo, local), vector in zip(fetched, vectors):
                if vector is None:
                    log.warning("Could not embed photo %s; skipped", photo.id)
                    skipped += 1
                else:
                    batch[photo.id] = vector
                if os.path.exists(local):
                    os.remove(local)
            if batch:
                store.save_embeddings(batch)
                embedded += len(batch)
            log.info("Embedded %d of %d", embedded, len(todo))
    summary = Summary(photos=len(photos), embedded=embedded, skipped=skipped)
    log.info("Done: %s", summary)
    return summary
