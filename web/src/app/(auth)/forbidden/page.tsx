/*
 * Render the staff access-denied message.
 * Author: Enfrai
 * Date: 25 Oct 2026
 */

import SessionShell from "@/components/session-shell";

/*
 * Render the forbidden interface and its associated content.
 */
export default function Forbidden() {
  return <SessionShell><p className="msg msg-error" role="alert">You do not have permission</p></SessionShell>;
}
