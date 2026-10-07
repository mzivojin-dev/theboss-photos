import { NextResponse } from "next/server";
import { GoogleAuth } from "google-auth-library";

const PROJECT_ID = process.env.GCP_PROJECT_ID!;
const REGION = process.env.GCP_REGION!;
const JOB_NAME = process.env.INGEST_JOB_NAME!;

export async function POST() {
  try {
    const triggerMode = process.env.INGEST_TRIGGER_MODE ?? "cloud";
    if (triggerMode === "local") {
      const serviceUrl = process.env.INGEST_SERVICE_URL;
      if (!serviceUrl) {
        throw new Error("INGEST_SERVICE_URL is required when INGEST_TRIGGER_MODE=local");
      }

      const response = await fetch(`${serviceUrl}/trigger`, { method: "POST" });
      const body = await response.json();
      return NextResponse.json(body, { status: response.status });
    }
    if (triggerMode !== "cloud") {
      throw new Error(`Unsupported INGEST_TRIGGER_MODE: ${triggerMode}`);
    }

    const auth = new GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/cloud-platform"],
    });
    const token = await auth.getAccessToken();

    const apiUrl =
      `https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}` +
      `/jobs/${JOB_NAME}:run`;

    const res = await fetch(apiUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    if (!res.ok) {
      throw new Error(`Cloud Run API ${res.status}: ${await res.text()}`);
    }

    const body = await res.json();
    return NextResponse.json({ executionName: body.name });
  } catch (err) {
    console.error("[ingest/trigger]", err);
    return NextResponse.json({ error: (err as Error).message }, { status: 500 });
  }
}
