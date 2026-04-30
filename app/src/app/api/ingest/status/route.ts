import { NextResponse } from "next/server";
import { GoogleAuth } from "google-auth-library";

const PROJECT_ID = process.env.GCP_PROJECT_ID!;
const REGION = process.env.GCP_REGION!;
const JOB_NAME = process.env.INGEST_JOB_NAME!;

type Status = "RUNNING" | "SUCCEEDED" | "FAILED" | "IDLE";

export async function GET() {
  try {
    const auth = new GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/cloud-platform"],
    });
    const token = await auth.getAccessToken();

    const apiUrl =
      `https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}` +
      `/jobs/${JOB_NAME}/executions?pageSize=1`;

    const res = await fetch(apiUrl, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) {
      throw new Error(`Cloud Run API ${res.status}: ${await res.text()}`);
    }

    const body = await res.json();
    const latest = body.executions?.[0];

    if (!latest) {
      return NextResponse.json({ status: "IDLE" as Status });
    }

    const conditions: { type: string; state: string }[] = latest.conditions ?? [];
    const completedCondition = conditions.find((c) => c.type === "Completed");

    let status: Status = "RUNNING";
    if (completedCondition?.state === "CONDITION_SUCCEEDED") {
      status = "SUCCEEDED";
    } else if (completedCondition?.state === "CONDITION_FAILED") {
      status = "FAILED";
    }

    return NextResponse.json({
      status,
      startedAt: latest.createTime ?? null,
      completedAt: latest.completionTime ?? null,
    });
  } catch (err) {
    console.error("[ingest/status]", err);
    return NextResponse.json(
      { status: "IDLE" as Status, error: (err as Error).message },
      { status: 500 }
    );
  }
}
