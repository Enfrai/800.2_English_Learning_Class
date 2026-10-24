/* Keep the login session id in this browser, shared by all its tabs.
 * The User Service expects it as "Authorization: Bearer <sessionid>".
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

const SESSION_KEY = "ako.sessionid";

export function getSessionId(): string | null {
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch {
    // Storage can be blocked (private mode, privacy settings).
    return null;
  }
}

export function saveSessionId(sessionId: string): void {
  try {
    window.localStorage.setItem(SESSION_KEY, sessionId);
  } catch {
    // Without storage the person is asked to log in again.
  }
}

export function clearSessionId(): void {
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}
