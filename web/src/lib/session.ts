/*
 * Read staff session state and select role-specific navigation destinations.
 * Author: willtbing
 * Date: 23 Oct 2026
 */

export type Role = "teacher" | "coordinator";
export type Session = { user_id: string; display_name: string; role: Role; expiresAt: number };
/*
 * Choose the staff home route for the authenticated role.
 */
export const homeFor = (role: Role) => role === "teacher" ? "/teacher" : "/coordinator";

/*
 * Fetch and validate the current staff identity and session expiry.
 */
export async function readSession(): Promise<Session | null> {
  const response = await fetch("/api/user/session", { cache: "no-store", credentials: "same-origin" });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Unable to check your session. Please try again.");
  const user = await response.json();
  const expiresAt = Date.parse(response.headers.get("X-Session-Expires-At") ?? "");
  if (!["teacher", "coordinator"].includes(user.role) || !Number.isFinite(expiresAt)) {
    throw new Error("Unable to verify your session.");
  }
  return { ...user, expiresAt };
}

/** Remove dev's legacy browser token; new logins use only the HttpOnly cookie. */
export function clearSessionId(): void {
  try { window.localStorage.removeItem("ako.sessionid"); } catch { /* Storage may be disabled. */ }
}
