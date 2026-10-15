"""
Tests for photo_embeddings: which photos the Embedding Job embeds, what it writes, and what it skips.
Also the text-embedding server's request handling.
"""
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.embed_server import handler
from src.photo_embeddings import MODEL_ID, IndexedPhoto, run


class Store:
    def __init__(self, photos):
        self._photos = photos
        self.writes: list[dict[str, list[float]]] = []

    def photos(self):
        return self._photos

    def save_embeddings(self, embeddings):
        self.writes.append(dict(embeddings))

    def saved(self):
        return {photo_id: vector for write in self.writes for photo_id, vector in write.items()}


class Previews:
    """Writes a placeholder file per preview; paths in `missing` are not in the bucket."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.fetched = []

    def fetch(self, preview_path, directory):
        self.fetched.append(preview_path)
        if preview_path in self.missing:
            return None
        local = f"{directory}/{preview_path.replace('/', '_')}"
        with open(local, "w") as f:
            f.write(preview_path)
        return local


class Embedder:
    """Embeds a file as [length of its name]; files whose content is in `unreadable` give None."""

    def __init__(self, unreadable=()):
        self.unreadable = set(unreadable)

    def embed_images(self, paths):
        result = []
        for path in paths:
            with open(path) as f:
                content = f.read()
            result.append(None if content in self.unreadable else [float(len(content))])
        return result


def photo(id, model=None, preview=True):
    return IndexedPhoto(id, f"previews/{id}.webp" if preview else None, model)


def test_photos_without_a_vector_from_the_current_model_are_embedded():
    store = Store([photo("new"), photo("old", model="open_clip/ViT-B-32/openai"), photo("done", model=MODEL_ID)])
    summary = run(store, Previews(), Embedder())
    assert sorted(store.saved()) == ["new", "old"]
    assert summary.embedded == 2


def test_running_again_after_everything_is_embedded_writes_nothing():
    store = Store([photo("a", model=MODEL_ID), photo("b", model=MODEL_ID)])
    previews = Previews()
    summary = run(store, previews, Embedder())
    assert store.writes == [] and previews.fetched == []
    assert summary.embedded == 0


def test_a_photo_that_cant_be_embedded_is_skipped_and_the_rest_are_saved():
    store = Store([photo("gone"), photo("broken"), photo("fine")])
    summary = run(store, Previews(missing={"previews/gone.webp"}), Embedder(unreadable={"previews/broken.webp"}))
    assert list(store.saved()) == ["fine"]
    assert summary.skipped == 2 and summary.embedded == 1


def test_a_photo_without_a_preview_is_not_fetched():
    store = Store([photo("no-preview", preview=False)])
    previews = Previews()
    run(store, previews, Embedder())
    assert previews.fetched == [] and store.writes == []


def test_each_batch_is_saved_as_it_is_done():
    store = Store([photo(str(i)) for i in range(5)])
    run(store, Previews(), Embedder(), batch_size=2)
    assert [sorted(w) for w in store.writes] == [["0", "1"], ["2", "3"], ["4"]]


def test_vectors_are_saved_against_the_right_photo():
    store = Store([photo("a"), photo("bbbb")])
    run(store, Previews(), Embedder())
    assert store.saved() == {"a": [float(len("previews/a.webp"))], "bbbb": [float(len("previews/bbbb.webp"))]}


# --- The text-embedding server ---------------------------------------------------------------------

def serve(embed_text):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(embed_text))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def post(server, body: bytes, path="/embed"):
    request = Request(f"http://127.0.0.1:{server.server_port}{path}", data=body,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request) as response:
            return response.status, json.loads(response.read())
    except HTTPError as err:
        return err.code, json.loads(err.read())


def test_the_server_embeds_text_and_names_the_model():
    server = serve(lambda text: [1.0, float(len(text))])
    try:
        assert post(server, json.dumps({"text": "  beach "}).encode()) == (200, {"model": MODEL_ID, "embedding": [1.0, 5.0]})
    finally:
        server.shutdown()


def test_the_server_refuses_empty_too_long_or_malformed_text():
    server = serve(lambda text: [0.0])
    try:
        assert post(server, json.dumps({"text": "   "}).encode())[0] == 400
        assert post(server, json.dumps({"text": "x" * 501}).encode())[0] == 400
        assert post(server, b"not json")[0] == 400
        assert post(server, json.dumps(["text"]).encode())[0] == 400
        assert post(server, json.dumps({"text": "a"}).encode(), path="/other")[0] == 404
    finally:
        server.shutdown()
