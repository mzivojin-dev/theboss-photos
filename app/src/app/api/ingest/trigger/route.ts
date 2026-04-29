import { NextResponse } from "next/server";
import { google } from "googleapis";

const PROJECT_ID = process.env.GCP_PROJECT_ID!;
const REGION = process.env.GCP_REGION!;
const JOB_NAME = process.env.INGEST_JOB_NAME!;

export async function POST() {
  const auth = new google.auth.GoogleAuth({
    scopes: ["https://www.googleapis.com/auth/cloud-platform"],
  });
  const client = await auth.getClient();

  const run = google.run({ version: "v2", auth: client as any });

  const response = await run.projects.locations.jobs.run({
    name: `projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}`,
    requestBody: {},
  });

  return NextResponse.json({ executionName: response.data.name });
}
