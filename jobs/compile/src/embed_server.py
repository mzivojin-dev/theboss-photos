"""
Embeds search text with the same model as the photos, for the app's /api/search. A Cloud Run
service (theboss-photos-embed-text) that only the app's service account may call; run it locally
with

    python -m src.embed_server

    POST /embed  {"text": "kids on a beach"}  ->  {"model": MODEL_ID, "embedding": [...]}

The model loads before the port opens, so Cloud Run sends no request until it is ready.
"""
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .photo_embeddings import MODEL_ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MAX_TEXT = 500  # characters; the model reads 64 tokens anyway


def handler(embed_text):
    lock = threading.Lock()  # one query at a time keeps memory flat; each takes tens of milliseconds

    class EmbedRequestHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/embed":
                return self._reply(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                text = json.loads(self.rfile.read(length)).get("text")
            except (ValueError, AttributeError):
                return self._reply(400, {"error": "expected JSON {\"text\": ...}"})
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                return self._reply(400, {"error": f"text must be 1-{MAX_TEXT} characters"})
            with lock:
                embedding = embed_text(text.strip())
            self._reply(200, {"model": MODEL_ID, "embedding": embedding})

        def _reply(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass  # the text people search for stays out of the logs

    return EmbedRequestHandler


def main() -> None:
    from .siglip import SiglipEmbedder

    embedder = SiglipEmbedder()
    port = int(os.environ.get("PORT", "8081"))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler(embedder.embed_text))
    log.info("Embedding %s text on port %d", MODEL_ID, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
