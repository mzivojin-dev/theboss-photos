import { NextResponse } from "next/server";
import { google } from "googleapis";

const PROJECT_ID = process.env.GCP_PROJECT_ID!;
const REGION = process.env.GCP_REGION!;
const JOB_NAME = process.env.INGEST_JOB_NAME!;

type Status = "RUNNING" | "SUCCEEDED" | "FAILED" | "IDLE";

export async function GET() {
  const auth = new google.auth.GoogleAuth({
    scopes: ["https://www.googleapis.com/auth/cloud-platform"],
  });
  const client = await auth.getClient();
  const run = google.run({ version: "v2", auth: client as any });

  const executions = await run.projects.locations.jobs.executions.list({
    parent: `projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}`,
    pageSize: 1,
  });

  const latest = executions.data.executions?.[0];
  if (!latest) {
    return NextResponse.json({ status: "IDLE" as Status });
  }

  const conditions = latest.conditions ?? [];
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
}
