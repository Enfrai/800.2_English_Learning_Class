/* Call the Accessment Service attendance endpoints through Nginx (US-004).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 * Updated: Pei Wu, 25 Oct 2026 (US-015 corrections and change history)
 */

import { apiRequest, RequestFailedError } from "./api";
import { type Learner, throwIfFieldError } from "./learners-api";

export type AttendanceRecord = {
  learner_id: string;
  status: string;
  recorded_by: string;
  recorded_at: string;
};

export type AttendanceList = {
  session_date: string;
  /** False for a session before today: only a coordinator can correct it. */
  editable: boolean;
  present_count: number;
  records: AttendanceRecord[];
  /** Learners whose attendance was corrected after the class, present or not. */
  corrected_learner_ids: string[];
};

export type AttendanceChange = {
  present_count: number;
  attendance: AttendanceRecord | null;
};

export type AddAndMarkResult = AttendanceChange & {
  learner: Pick<Learner, "id" | "first_name" | "family_name" | "first_language" | "contact">;
  /** False when a learner with the same name was already on the list. */
  learner_added: boolean;
};

/** One entry of a past class's change history (US-015). */
export type Correction = {
  learner_id: string;
  /** Null when the learner is no longer known to the User Service. */
  learner_name: string | null;
  old_status: string;
  new_status: string;
  corrected_by: string;
  corrected_by_name: string | null;
  reason: string | null;
  created_at: string;
};

/** The learner is already marked present. No second record was made. */
export class AlreadySignedInError extends Error {
  readonly record: AttendanceRecord;

  /*
   * Initialize the error instance and retain the supplied message and structured
   * details.
   */
  constructor(message: string, record: AttendanceRecord) {
    super(message);
    this.record = record;
  }
}

/** The session is before today. The message comes from the server. */
export class PastSessionError extends Error {}

/** The class is today, so it is changed on its list, not corrected. */
export class SessionNotPastError extends Error {}

/** The session, the learner or the present record does not exist. */
export class NotFoundError extends Error {}

/*
 * Send the feature API request and translate its response into data or a typed error.
 */
async function send<T>(url: string, init: RequestInit = {}): Promise<T> {
  const { status, body, detail, message } = await apiRequest(url, init);
  if (status >= 200 && status < 300) return body as T;
  if (status === 409 && detail?.attendance) {
    throw new AlreadySignedInError(String(detail.message), detail.attendance as AttendanceRecord);
  }
  if (status === 409) throw new SessionNotPastError(message);
  if (status === 403) throw new PastSessionError(message);
  if (status === 404) throw new NotFoundError(message);
  throwIfFieldError(status, detail);
  throw new RequestFailedError();
}

/*
 * Build the attendance endpoint for the encoded class-session identifier.
 */
function attendanceUrl(sessionId: string): string {
  return `/api/access/sessions/${encodeURIComponent(sessionId)}/attendance`;
}

/*
 * Load the class attendance list and current present count.
 */
export function getAttendance(sessionId: string): Promise<AttendanceList> {
  return send<AttendanceList>(attendanceUrl(sessionId));
}

/*
 * Mark the selected learner present for the class session.
 */
export function markPresent(sessionId: string, learnerId: string): Promise<AttendanceChange> {
  return send<AttendanceChange>(attendanceUrl(sessionId), {
    method: "POST",
    body: JSON.stringify({ learner_id: learnerId }),
  });
}

/*
 * Remove the learner’s present attendance mark.
 */
export function unmarkPresent(sessionId: string, learnerId: string): Promise<AttendanceChange> {
  return send<AttendanceChange>(`${attendanceUrl(sessionId)}/${encodeURIComponent(learnerId)}`, {
    method: "DELETE",
  });
}

/*
 * Create or find the learner and mark them present through the attendance API.
 */
export function addAndMarkPresent(
  sessionId: string,
  name: { first_name: string; family_name: string },
): Promise<AddAndMarkResult> {
  return send<AddAndMarkResult>(`${attendanceUrl(sessionId)}/new-learner`, {
    method: "POST",
    body: JSON.stringify(name),
  });
}

/*
 * Build the historical-corrections endpoint for the class session.
 */
function correctionsUrl(sessionId: string): string {
  return `/api/access/sessions/${encodeURIComponent(sessionId)}/corrections`;
}

/** A coordinator marks a learner present or not present at a past class (US-015). */
export function correctAttendance(
  sessionId: string,
  learnerId: string,
  present: boolean,
): Promise<AttendanceChange> {
  return send<AttendanceChange>(correctionsUrl(sessionId), {
    method: "POST",
    body: JSON.stringify({ learner_id: learnerId, present }),
  });
}

/** Every correction of a past class, oldest first. Coordinators only. */
export function getCorrections(sessionId: string): Promise<Correction[]> {
  return send<Correction[]>(correctionsUrl(sessionId));
}
