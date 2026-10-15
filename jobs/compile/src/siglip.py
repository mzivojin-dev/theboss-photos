"""
The embedding model (MODEL_ID in photo_embeddings.py), run on CPU with open_clip. Images and text
land in one space, so a text query's vector is compared directly with the photos' vectors. The
weights are baked into the image (see Dockerfile), so nothing is downloaded at run time.
"""
import logging
from typing import Optional

import open_clip
import torch
from PIL import Image

from .photo_embeddings import MODEL_NAME, PRETRAINED

log = logging.getLogger(__name__)


class SiglipEmbedder:
    def __init__(self):
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer(MODEL_NAME)

    def embed_images(self, paths: list[str]) -> list[Optional[list[float]]]:
        tensors: list[Optional[torch.Tensor]] = []
        for path in paths:
            try:
                with Image.open(path) as image:
                    tensors.append(self._preprocess(image.convert("RGB")))
            except Exception as err:
                log.warning("Could not read %s: %s", path, err)
                tensors.append(None)
        readable = [t for t in tensors if t is not None]
        if not readable:
            return [None] * len(paths)
        with torch.no_grad():
            vectors = iter(_unit(self._model.encode_image(torch.stack(readable))))
        return [next(vectors) if t is not None else None for t in tensors]

    def embed_text(self, text: str) -> list[float]:
        with torch.no_grad():
            return _unit(self._model.encode_text(self._tokenizer([text])))[0]


def _unit(vectors: torch.Tensor) -> list[list[float]]:
    return torch.nn.functional.normalize(vectors, dim=-1).tolist()
