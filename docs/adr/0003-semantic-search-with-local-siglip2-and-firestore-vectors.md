# 3. Semantic search with a local SigLIP2 model and Firestore vector search

Date: 2026-10-15. Status: accepted.

## Context

Issue #39: search the library by meaning ("kids on a beach at sunset") rather than only by scrolling. It is also a learning project for retrieval, so an LLM answering layer may come later on top of the retrieval built here. Search is read-only and hides nothing.

A spike on 200 random Previews compared three open_clip models (notes in `docs/spikes/semantic-search-models.md`).

## Decision

- **Model: `ViT-B-16-SigLIP2` (webli), via open_clip on CPU.** It ranked about as well as `ViT-SO400M-14-SigLIP` at ~1/4.6 the time per image (157 ms vs 723 ms) and ~half the memory (2.1 vs 3.8 GiB). It clearly beat `ViT-B-32` (laion2b) on food, and on non-English queries ("deca na plazi"), which B-32 got wrong. It makes 768-dimension vectors. Vertex AI `multimodalembedding` was not chosen: it is paid per image and teaches less.
- **Vectors in the Photo Index, searched with Firestore `findNearest` (COSINE).** No new store. Each vector carries `embedding_model`, and the job re-embeds any photo whose vector came from another model. The query filters on `embedding_model ==` the model the embed-text service reports, so a query is never compared with vectors from another model. That needs a composite vector index (`embedding_model`, then `embedding`, flat), which lives in `infra/firestore.tf`.
- **An Embedding Job** (`python -m src.embed_main`, Cloud Run job `theboss-photos-embed`, compile image) embeds Previews. The Ingestion Job starts it after a run that indexed anything, like the Grouping Job.
- **Search text is embedded by a small private Cloud Run service** (`theboss-photos-embed-text`, `python -m src.embed_server`, same image and model). The query and the index must use the same model, and that model runs in Python, so the Next.js app calls this service with an ID token and then runs the vector query itself. It scales to zero.
- **A date range is applied after the vector query.** Firestore does not document range filters inside `findNearest`, so `/api/search` asks for up to 1000 neighbours and drops those outside the range. That is exact while fewer than 1000 photos are embedded. The range is a pair of instants, and the search box sends the user's local midnights, so the days match the Timeline's local days.
- **Results show Similar Group covers only.** A matching photo hidden behind a cover appears as that cover, at the rank of the group's best match.

## Consequences

- The compile image gains CPU torch, open_clip and the baked-in weights (measured: +1.7 GB compressed, +2.7 GB unpacked).
- With min instances 0, the first search after a quiet spell waits ~20 s for the model to load. A min instance of 1 would remove that wait at an always-on cost.
- Beyond 1000 embedded photos a narrow date range can miss matches. Then add a composite vector index with `taken_at` and prefilter in the query (verify that range prefilters are supported first).
- Nearest-neighbour search always returns something: a query with no true match (no dogs in the library) still returns the closest photos. There is no score threshold yet; SigLIP2 cosine scores are small (~0.05–0.15) and do not separate hits from misses on their own.
- Changing the model means a new `MODEL_ID`, a new index if the dimension changes, and one full re-embedding run. Until that run finishes, search covers only the photos already re-embedded: the others are left out, not ranked wrongly. Deploy the new embed-text service after the run, not before, to avoid that gap.
- Videos are not embedded for now (they have no Preview). Captions/OCR (phase 4) and an LLM "ask" layer (phase 5) are not decided here.
