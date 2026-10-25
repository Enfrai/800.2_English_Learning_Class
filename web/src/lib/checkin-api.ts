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

const DEVICE_ID_KEY = "ako.signin-device";

function randomUuid(): string {
  // crypto.randomUUID needs HTTPS; getRandomValues works on plain HTTP too.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * A random id for this phone, so wrong names are counted per phone rather
 * than per Wi-Fi address (NFR-11). It is not built from device details.
 */
function deviceId(): string {
  try {
    const saved = window.localStorage.getItem(DEVICE_ID_KEY);
    if (saved) return saved;
    const created = randomUuid();
    window.localStorage.setItem(DEVICE_ID_KEY, created);
    return created;
  } catch {
    // Storage blocked: the server falls back to the stricter address limit.
    return "";
  }
}

function checkinUrl(token: string): string {
  return `/api/access/checkin/${encodeURIComponent(token)}`;
}

async function send(
  url: string,
  init?: RequestInit,
  headers: Record<string, string> = {},
): Promise<Response | null> {
  try {
    return await fetch(url, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...headers },
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
  const id = deviceId();
  const response = await send(
    `${checkinUrl(token)}/sign-in`,
    {
      method: "POST",
      body: JSON.stringify({ first_name: firstName, family_name: familyName }),
    },
    id ? { "X-Device-Id": id } : {},
  );
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
