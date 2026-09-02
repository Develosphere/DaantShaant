import type { PipelineResult } from "./types";
import { authorizedFetch } from "./portal-auth";

const API_BASE =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export function getWsUrl(): string {
  const base = process.env.NEXT_PUBLIC_ORCHESTRATOR_WS ?? "ws://127.0.0.1:8000";
  return `${base}/v1/live/session`;
}

export async function analyzeSnapshot(
  imageBase64: string,
  imageMimeType = "image/jpeg"
): Promise<PipelineResult> {
  const res = await authorizedFetch("patient", `${API_BASE}/v1/teeth/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_base64: imageBase64,
      image_mime_type: imageMimeType,
      locale: "en",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    let friendlyMessage = "We couldn't complete the screening right now. Please try again.";
    const detail = err.detail;
    if (typeof detail === "object" && detail !== null) {
      if (detail.code === "downstream_unavailable" || detail.code === "downstream_error") {
        friendlyMessage = "Screening service is temporarily busy or unavailable. Please try again in a moment.";
      } else if (detail.code === "timeout") {
        friendlyMessage = "Analysis took longer than expected. Please retry.";
      } else if (typeof detail.detail === "string" && detail.detail) {
        friendlyMessage = detail.detail;
      }
    } else if (typeof detail === "string" && detail.length > 0) {
      if (detail.includes("downstream_unavailable") || detail.includes("Connection refused")) {
        friendlyMessage = "Screening services are currently unavailable. Please check your backend connection.";
      } else {
        friendlyMessage = detail;
      }
    } else if (res.status === 504 || res.status === 408) {
      friendlyMessage = "Analysis took longer than expected. Please retry.";
    }
    throw new Error(friendlyMessage);
  }
  const data = (await res.json()) as PipelineResult;
  if (data.status === "rejected") {
    const reason = data.relevance?.reason || "This image doesn't appear suitable for oral screening.";
    throw new Error(reason);
  }
  if (data.status === "retake") {
    const reason = data.relevance?.retake_reason || "Please take another photo with your mouth/teeth more clearly visible.";
    throw new Error(reason);
  }
  return data;
}
