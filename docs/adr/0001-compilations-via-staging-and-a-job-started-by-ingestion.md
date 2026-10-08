# 1. Compilations: staging plus a job started by ingestion, no message queue

Date: 2026-10-08. Status: accepted.

## Context

Trip videos (Compilations) need every clip and photo of a Trip. A Trip's media can arrive across several Takeout Archives and several ingestion runs. Originals sit in GCS Archive storage, which charges for every read. The Ingestion Job already holds each file's bytes in memory while it indexes it. The design was prototyped on the `prototype/compilation-videos` branch (see `jobs/compilation-prototype/README.md` there).

## Decision

- The Ingestion Job copies each newly indexed video, and a 1920px JPEG of each photo, to a **Staging** bucket (Standard storage, 30-day expiry) while it has the bytes.
- After a run that indexed anything, the Ingestion Job starts the **Compilation Job** once, through the Cloud Run Admin API (`jobs.run`).
- The Compilation Job recomputes the Trips from the Photo Index and makes a Compilation only for Trips whose membership changed. Each Compilation's status is kept in the `compilations` collection, so re-runs are safe and failed Trips are retried. Cloud Run's `--tasks N` splits Trips across tasks.
- No AI: highlights come from ffmpeg measurements (loudness, motion, brightness) and photos are ranked by OpenCV face detection.
- Compilations are stored in GCS and served by signed URL, not uploaded to YouTube.

## Alternatives considered

- **A message queue (Pub/Sub, Cloud Tasks).** The unit of work is a Trip, not a file, so per-file messages would need a debounce or barrier. Cloud Run Jobs don't consume subscriptions, and the payload is gigabytes, beyond Pub/Sub's 10 MB message limit. Firestore state already makes re-runs safe. This should be revisited for many users or continuous ingestion.
- **Analysing clips during ingestion.** That would put ffmpeg, OpenCV and more CPU into the Ingestion Job. Staging the bytes keeps it lean.
- **Claude analysing sampled frames.** It produced better edits (about $0.02 per clip on Sonnet), but was judged not worth the cost for now.
- **YouTube hosting.** Videos from an unaudited API project are locked to private, and private videos don't play embedded in the app.

## Consequences

- Media indexed before staging existed, or more than 30 days ago, has no staged copy. The Compilation Job then reads the video's Original (an Archive retrieval charge) and the photo's 1280px Preview.
- Compilations are HDR HEVC when most footage is HDR. Browsers without HEVC support (Firefox, some Windows setups) need a standard-range H.264 copy, which isn't made yet.
- Rendering is CPU-bound: about 3.5 times the video's length in local Docker tests, so the job gets 8 vCPUs. Its disk is in memory (a Trip's clips, segments and output sit there at once), hence 16 GiB.
