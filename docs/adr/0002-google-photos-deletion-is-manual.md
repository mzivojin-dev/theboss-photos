# 2. Deleting from Google Photos is manual, guided by safe days

Date: 2026-10-09. Status: accepted.

## Context

The goal is to delete photos from Google Photos once they are safely in GCS. Google offers no API for that: the Library API never had a delete call, and since 31 March 2025 it only sees media an app created itself. The Picker API strips GPS. Browser automation was rejected as fragile and a ToS gray area.

## Decision

- Deletion stays manual, in the Photos web UI. The app shows **safe days** (see *Safe Day* in `CONTEXT.md`) and the user deletes those in Photos, then marks them deleted in the app.
- To call a day safe the app must know what ingestion did not index and what each export covered, so the Ingestion Job records an **Ingestion Ledger** (`takeout_problems`, `takeout_exports`).
- Deleted items stay in Photos Trash for 60 days, which leaves room to recover from a mistake.

## Consequences

- A photo taken before an export but added to Google Photos after it is in no archive; the cleanup page states this residual risk.
- Stopping Photos backup on the phone is a possible later step, not decided here.
