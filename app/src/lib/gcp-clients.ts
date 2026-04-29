import { Firestore } from "@google-cloud/firestore";
import { Storage } from "@google-cloud/storage";

const PROJECT_ID = process.env.GCP_PROJECT_ID!;

export const db = new Firestore({ projectId: PROJECT_ID });
export const storage = new Storage({ projectId: PROJECT_ID });
export const previewsBucket = storage.bucket(process.env.PREVIEWS_BUCKET!);
export const originalsBucket = storage.bucket(process.env.ORIGINALS_BUCKET!);
