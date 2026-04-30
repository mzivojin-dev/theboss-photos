import { Firestore } from "@google-cloud/firestore";
import { Storage } from "@google-cloud/storage";

let _db: Firestore | undefined;
let _storage: Storage | undefined;

export function db() {
  return (_db ??= new Firestore({ projectId: process.env.GCP_PROJECT_ID!, databaseId: "photo-lib", preferRest: true }));
}

export function storage() {
  return (_storage ??= new Storage({ projectId: process.env.GCP_PROJECT_ID! }));
}

export function previewsBucket() {
  return storage().bucket(process.env.PREVIEWS_BUCKET!);
}

export function originalsBucket() {
  return storage().bucket(process.env.ORIGINALS_BUCKET!);
}
