import { GoogleAuth } from "google-auth-library";

export interface TextEmbedding {
  model: string;
  embedding: number[];
}

let _auth: GoogleAuth | undefined;

/**
 * Embeds search text with the same model as the photos, through the embed-text service
 * (jobs/compile/src/embed_server.py). In Cloud Run the service is private, so the request carries
 * an ID token for the app's service account; locally it is plain HTTP to the compose service.
 */
export async function embedText(text: string, serviceUrl = process.env.EMBED_SERVICE_URL): Promise<TextEmbedding> {
  if (!serviceUrl) throw new Error("EMBED_SERVICE_URL is not set");
  const url = `${serviceUrl.replace(/\/$/, "")}/embed`;
  const headers = new Headers({ "Content-Type": "application/json" });
  if (url.startsWith("https://")) {
    const client = await (_auth ??= new GoogleAuth()).getIdTokenClient(serviceUrl);
    new Headers(await client.getRequestHeaders()).forEach((value, name) => headers.set(name, value));
  }
  // The service scales to zero; a cold start loads the model first.
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ text }),
    signal: AbortSignal.timeout(90_000),
  });
  if (!res.ok) throw new Error(`embed-text service answered ${res.status}: ${await res.text()}`);
  return res.json();
}
