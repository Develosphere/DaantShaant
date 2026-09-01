import { getStoredUser } from "./portal-auth";

/** The canonical PostgreSQL users.id UUID for the authenticated patient. */
export function getUserId(): string {
  if (typeof window === "undefined") return "";
  return getStoredUser("patient")?.user_id ?? "";
}

/** Local UI key only; it is never used as application identity. */
export function getPatientConversationStorageKey(): string {
  const userId = getUserId();
  return userId
    ? `dantshaant_patient_conversation_${userId}`
    : "dantshaant_current_conversation";
}
