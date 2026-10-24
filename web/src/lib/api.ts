/* Send requests to the Ako services through Nginx with the login session.
 * Author: Pei Wu
 * Date: 23 Oct 2026
 * Updated: Sandhya Tiwari, 23 Oct 2026 (US-006 file uploads and downloads)
 */

import { getSessionId } from "./session";

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
 * Send a request with "Authorization: Bearer <sessionid>".
 * A FormData body (a file upload) is sent as multipart form data; any other
 * body is sent as JSON. Throws LoginRequiredError for a missing or ended
 * session and RequestFailedError when the server cannot be reached.
 */
async function fetchWithSession(url: string, init: RequestInit): Promise<Response> {
  const sessionId = getSessionId();
  if (!sessionId) throw new LoginRequiredError();

  const headers: Record<string, string> = { Authorization: `Bearer ${sessionId}` };
  // The browser sets the multipart boundary itself, so no type is given for FormData.
  if (!(init.body instanceof FormData)) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch {
    throw new RequestFailedError();
  }
  if (response.status === 401) throw new LoginRequiredError();
  return response;
}

/**
 * Send a request and read the JSON answer. Throws as fetchWithSession does;
 * every other answer is returned so the caller can translate it.
 */
export async function apiRequest(url: string, init: RequestInit = {}): Promise<ApiResponse> {
  const response = await fetchWithSession(url, init);
  const body: unknown = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return {
    status: response.status,
    body,
    detail: typeof detail === "object" && detail !== null ? (detail as Record<string, unknown>) : undefined,
    message: typeof detail === "string" ? detail : undefined,
  };
}

/**
 * Fetch a file with the login session. A plain link cannot send the
 * Authorization header, so downloads go through here. Returns the response
 * for a 2xx answer and its status otherwise.
 */
export async function apiFile(url: string): Promise<{ status: number; blob: Blob | null }> {
  const response = await fetchWithSession(url, {});
  if (!response.ok) return { status: response.status, blob: null };
  return { status: response.status, blob: await response.blob() };
}
