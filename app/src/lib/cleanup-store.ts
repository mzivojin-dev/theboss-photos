import { CleanupRepository, type CleanupStore } from "./cleanup-repository";
import { FakeCleanupStore } from "./fake-cleanup-store";
import { db, originalsBucket } from "./gcp-clients";

/** The real store, or with CLEANUP_FAKE_DATA=true an in-memory one with sample data (no GCP access). */
export function cleanupStore(): CleanupStore {
  return process.env.CLEANUP_FAKE_DATA === "true" ? FakeCleanupStore.shared() : new CleanupRepository(db(), originalsBucket());
}
