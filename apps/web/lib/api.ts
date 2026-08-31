import type { PipelineResult } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export function getWsUrl(): string {
  const base = process.env.NEXT_PUBLIC_ORCHESTRATOR_WS ?? "ws://127.0.0.1:8000";
  return `${base}/v1/live/session`;
}

export { getUserId } from "./user-id";

export async function analyzeSnapshot(
  imageBase64: string,
  userId: string,
  imageMimeType = "image/jpeg"
): Promise<PipelineResult> {
  const res = await fetch(`${API_BASE}/v1/teeth/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      image_base64: imageBase64,
      image_mime_type: imageMimeType,
      locale: "en",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string"
        ? err.detail
        : JSON.stringify(err.detail ?? res.statusText)
    );
  }
  return res.json();
}
