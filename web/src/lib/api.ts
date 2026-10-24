/* Send requests to the Ako services through Nginx with the login session.
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */


/** No session, or the session has ended. */
export class LoginRequiredError extends Error {}

/** The server could not be reached or gave an unexpected answer. */
export class RequestFailedError extends Error {}

export type ApiResponse = {
  status: number;
  body: unknown;
  /** The "detail" field of an error answer, when it is an object. */
  detail: Record<string, unknown> | undefined;
  /** The "detail" field of an error answer, when it is text. */
  message: string | undefined;
};

/**
 * Send same-origin cookies; Attendance uses the server-only Bearer adapter.
 * Throws LoginRequiredError for a missing or ended session and
 * RequestFailedError when the server cannot be reached. Every other answer
 * is returned so the caller can translate it.
 */
export async function apiRequest(url: string, init: RequestInit = {}): Promise<ApiResponse> {
  // Attendance retains its Bearer contract without exposing the cookie to JavaScript.
  const target = url.startsWith("/api/access/")
    ? url.replace("/api/access/", "/api/staff/access/") : url;

  let response: Response;
  try {
    response = await fetch(target, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
      },
    });
  } catch {
    throw new RequestFailedError();
  }
  if (response.status === 401) throw new LoginRequiredError();

  const body: unknown = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return {
    status: response.status,
    body,
    detail: typeof detail === "object" && detail !== null ? (detail as Record<string, unknown>) : undefined,
    message: typeof detail === "string" ? detail : undefined,
  };
}
