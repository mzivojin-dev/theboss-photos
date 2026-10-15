# Spike: which embedding model for semantic search (#39)

Date: 2026-10-15. Throwaway code; only these notes are kept. Decision: ADR 0003.

## Setup

- 200 random photos (seed 39) out of 506 in the Photo Index, using their 1280px WebP Previews.
- Three open_clip models on CPU (16 threads, Python 3.12, torch 2.14.1+cpu). Images were embedded in batches of 16 with unit vectors, and each query was ranked by cosine.
- Ten text queries. For each model and query I put the top 8 photos on a contact sheet and looked at them.

## Numbers

| Model | Dims | ms / image | RSS | Weights load |
|---|---|---|---|---|
| `ViT-B-32` laion2b_s34b_b79k | 512 | 81 | 1.0 GiB | (first download) |
| **`ViT-B-16-SigLIP2` webli** | **768** | **157** | **2.1 GiB** | 15 s |
| `ViT-SO400M-14-SigLIP` webli | 1152 | 723 | 3.8 GiB | 16 s |

At 157 ms per image, 1M photos is ~44 CPU-hours, a few dollars of Cloud Run job time (estimate). The current library takes about a minute and a half.

## What the eye said

- **"kids on a beach at sunset"**: all three are good. They return the same beach photos of the kids, and the sunset shots rank first.
- **"food on a plate"**: both SigLIP models are good (restaurant tables, fries, a tray of cherries). B-32 mixed in an appliance label and a kid in a kitchen.
- **"a city at night"**: all fine: the lit heart sculpture, the Trevi fountain at dusk, a concert stage.
- **"deca na plazi"** (Serbian: children on the beach): both SigLIP models get it right. **B-32 fails**: it returns school groups in folk costume. Multilingual matters for this library.
- **"a screenshot of a phone"**: there are no screenshots in the sample. The SigLIP models return shop price tags and laptop screens, which are reasonable neighbours.
- **"a dog", "mountains", "a birthday cake with candles"**: the sample has none of these, so **every model returns junk**, with scores no lower than a real hit from a weaker query. Nearest-neighbour search always answers, and raw cosine scores don't say "no match".
- SO400M was not visibly better than SigLIP2 B/16 on any query.

## Side findings

- Several Previews are stored **sideways** (no EXIF orientation tag left, and ingestion already applies `exif_transpose`). These are probably phone photos whose rotation lives somewhere other than EXIF. That hurts both viewing and embedding. It is worth a separate issue.
- SigLIP2's tokenizer needs `transformers` installed (not `sentencepiece`). open_clip reads 64 tokens of text.

## Not tried

- Vertex AI `multimodalembedding` (paid; less to learn).
- Captions/OCR with a VLM (phase 4 of the issue).
