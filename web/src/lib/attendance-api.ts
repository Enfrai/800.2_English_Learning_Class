/* Call the Accessment Service attendance endpoints through Nginx (US-004).
 * Author: Pei Wu
 * Date: 23 Oct 2026
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

/** The learner is already marked present. No second record was made. */
export class AlreadySignedInError extends Error {
  readonly record: AttendanceRecord;

  constructor(message: string, record: AttendanceRecord) {
    super(message);
    this.record = record;
  }
}

/** The session is before today. The message comes from the server. */
export class PastSessionError extends Error {}

/** The session, the learner or the present record does not exist. */
export class NotFoundError extends Error {}

async function send<T>(url: string, init: RequestInit = {}): Promise<T> {
  const { status, body, detail, message } = await apiRequest(url, init);
  if (status >= 200 && status < 300) return body as T;
  if (status === 409 && detail?.attendance) {
    throw new AlreadySignedInError(String(detail.message), detail.attendance as AttendanceRecord);
  }
  if (status === 403) throw new PastSessionError(message);
  if (status === 404) throw new NotFoundError(message);
  throwIfFieldError(status, detail);
  throw new RequestFailedError();
}

function attendanceUrl(sessionId: string): string {
  return `/api/access/sessions/${encodeURIComponent(sessionId)}/attendance`;
}

export function getAttendance(sessionId: string): Promise<AttendanceList> {
  return send<AttendanceList>(attendanceUrl(sessionId));
}

export function markPresent(sessionId: string, learnerId: string): Promise<AttendanceChange> {
  return send<AttendanceChange>(attendanceUrl(sessionId), {
    method: "POST",
    body: JSON.stringify({ learner_id: learnerId }),
  });
}

export function unmarkPresent(sessionId: string, learnerId: string): Promise<AttendanceChange> {
  return send<AttendanceChange>(`${attendanceUrl(sessionId)}/${encodeURIComponent(learnerId)}`, {
    method: "DELETE",
  });
}

export function addAndMarkPresent(
  sessionId: string,
  name: { first_name: string; family_name: string },
): Promise<AddAndMarkResult> {
  return send<AddAndMarkResult>(`${attendanceUrl(sessionId)}/new-learner`, {
    method: "POST",
    body: JSON.stringify(name),
  });
}
