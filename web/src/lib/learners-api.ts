/* Call the User Service learner endpoints through Nginx (US-003).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

import { getSessionId } from "./session";

const LEARNERS_URL = "/api/user/learners";

export type Learner = {
  id: string;
  first_name: string;
  family_name: string;
  contact: string | null;
  first_language: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type LearnerDetails = {
  first_name: string;
  family_name: string;
  first_language: string;
  contact: string;
};

/** No session, or the session has ended. */
export class LoginRequiredError extends Error {}

/** One field breaks a rule. The message comes from the server. */
export class LearnerFieldError extends Error {
  readonly field: string;

  constructor(field: string, message: string) {
    super(message);
    this.field = field;
  }
}

/** Another learner has the same first and family name. */
export class DuplicateNameError extends Error {
  readonly duplicates: Learner[];

  constructor(message: string, duplicates: Learner[]) {
    super(message);
    this.duplicates = duplicates;
  }
}

/** The server could not be reached or gave an unexpected answer. */
export class RequestFailedError extends Error {}

async function send<T>(url: string, init: RequestInit = {}): Promise<T> {
  const sessionId = getSessionId();
  if (!sessionId) throw new LoginRequiredError();

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Authorization: `Bearer ${sessionId}`,
        "Content-Type": "application/json",
      },
    });
  } catch {
    throw new RequestFailedError();
  }
  if (response.ok) return (await response.json()) as T;

  const body: { detail?: unknown } | null = await response.json().catch(() => null);
  const detail = body?.detail as Record<string, unknown> | undefined;
  if (response.status === 401) throw new LoginRequiredError();
  if (response.status === 409 && Array.isArray(detail?.duplicates)) {
    throw new DuplicateNameError(String(detail.message), detail.duplicates as Learner[]);
  }
  if (response.status === 422 && typeof detail?.field === "string") {
    throw new LearnerFieldError(detail.field, String(detail.message));
  }
  throw new RequestFailedError();
}

export function listLearners(): Promise<Learner[]> {
  return send<Learner[]>(LEARNERS_URL);
}

export function addLearner(
  details: LearnerDetails,
  allowDuplicate: boolean,
): Promise<Learner> {
  return send<Learner>(LEARNERS_URL, {
    method: "POST",
    body: JSON.stringify({ ...details, allow_duplicate: allowDuplicate }),
  });
}

export function updateLearner(
  id: string,
  details: LearnerDetails,
  allowDuplicate: boolean,
): Promise<Learner> {
  return send<Learner>(`${LEARNERS_URL}/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ ...details, allow_duplicate: allowDuplicate }),
  });
}
