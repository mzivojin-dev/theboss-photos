"""
GCS adapter for the Media Indexer's Blob store port: one bucket.
"""
from google.cloud import storage


class GcsBlobStore:
    def __init__(self, bucket: storage.Bucket):
        self._bucket = bucket

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        self._bucket.blob(path).upload_from_string(data, content_type=content_type)
