/* Call the User Service learner endpoints through Nginx (US-003).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

import { apiRequest, RequestFailedError } from "./api";

export { LoginRequiredError, RequestFailedError } from "./api";

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

/** Throw the learner error for a 422 field answer, if it is one. */
export function throwIfFieldError(status: number, detail: Record<string, unknown> | undefined): void {
  if (status === 422 && typeof detail?.field === "string") {
    throw new LearnerFieldError(detail.field, String(detail.message));
  }
}

async function send<T>(url: string, init: RequestInit = {}): Promise<T> {
  const { status, body, detail } = await apiRequest(url, init);
  if (status >= 200 && status < 300) return body as T;
  if (status === 409 && Array.isArray(detail?.duplicates)) {
    throw new DuplicateNameError(String(detail.message), detail.duplicates as Learner[]);
  }
  throwIfFieldError(status, detail);
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
