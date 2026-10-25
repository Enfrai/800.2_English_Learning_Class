/* Call the public QR sign-in endpoints of the Accessment Service (US-012).
 * Learners have no login, so no cookie or session is sent.
 * Author: Pei Wu
 * Date: 25 Oct 2026
 */

// Message catalogue, UI design document section 7.
export const SIGNED_IN = "You are signed in";
export const NAME_NOT_FOUND = "We could not find that name. Please ask the teacher";
export const CHECKIN_CLOSED = "Check-in is closed. Please ask the teacher";
export const ALREADY_SIGNED_IN = "Already signed in";
// Not in the catalogue; to be agreed with the team.
export const UNAVAILABLE = "Sign-in is not working right now. Please ask the teacher";

export type CheckinState =
  | { kind: "open"; sessionDate: string }
  | { kind: "closed" }
  | { kind: "failed" };

export type SignInResult =
  | { kind: "signed-in"; sessionDate: string }
  | { kind: "already" }
  | { kind: "not-found" }
  | { kind: "closed" }
  | { kind: "too-many"; message: string }
  | { kind: "failed" };

function checkinUrl(token: string): string {
  return `/api/access/checkin/${encodeURIComponent(token)}`;
}

async function send(url: string, init?: RequestInit): Promise<Response | null> {
  try {
    return await fetch(url, {
      ...init,
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return null;
  }
}

async function detail(response: Response): Promise<string | undefined> {
  const body: unknown = await response.json().catch(() => null);
  const value = (body as { detail?: unknown } | null)?.detail;
  return typeof value === "string" ? value : undefined;
}

/** Find out whether check-in is open, and for which class (AC1, AC5). */
export async function getCheckin(token: string): Promise<CheckinState> {
  const response = await send(checkinUrl(token));
  if (!response) return { kind: "failed" };
  if (response.ok) {
    const body = (await response.json()) as { session_date: string };
    return { kind: "open", sessionDate: body.session_date };
  }
  return response.status === 404 ? { kind: "closed" } : { kind: "failed" };
}

/** Sign in with the typed name (AC2 to AC5). */
export async function signIn(
  token: string,
  firstName: string,
  familyName: string,
): Promise<SignInResult> {
  const response = await send(`${checkinUrl(token)}/sign-in`, {
    method: "POST",
    body: JSON.stringify({ first_name: firstName, family_name: familyName }),
  });
  if (!response) return { kind: "failed" };
  if (response.status === 201) {
    const body = (await response.json()) as { session_date: string };
    return { kind: "signed-in", sessionDate: body.session_date };
  }
  const message = await detail(response);
  if (response.status === 409) return { kind: "already" };
  if (response.status === 404) {
    return message === NAME_NOT_FOUND ? { kind: "not-found" } : { kind: "closed" };
  }
  if (response.status === 429 && message) return { kind: "too-many", message };
  return { kind: "failed" };
}
