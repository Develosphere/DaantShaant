import { getStoredUser } from "./portal-auth";

const LEGACY_KEY = "dantshaant_user_id";

/**
 * UUID for scan, chat, and live-session APIs.
 * Backend expects a standard UUID — portal MongoDB user_id must NOT be sent here.
 */
export function getUserId(): string {
  if (typeof window === "undefined") return "";

  const patient = getStoredUser("patient");
  if (patient?.user_id) {
    const mapKey = `dantshaant_clinical_user_${patient.user_id}`;
    let id = localStorage.getItem(mapKey);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(mapKey, id);
    }
    return id;
  }

  let id = localStorage.getItem(LEGACY_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(LEGACY_KEY, id);
  }
  return id;
}

/** localStorage key for patient-portal chat session (not sent to API). */
export function getPatientConversationStorageKey(): string {
  const patient = getStoredUser("patient");
  if (patient?.user_id) {
    return `dantshaant_patient_conversation_${patient.user_id}`;
  }
  return "dantshaant_current_conversation";
}
