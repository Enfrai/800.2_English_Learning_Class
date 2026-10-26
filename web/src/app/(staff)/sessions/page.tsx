/* Provide the staff class-session list and creation entry point (US-014).
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import SessionListScreen from "@/components/class-sessions/session-list";
export const metadata = { title: "Class sessions" };
export default function Page() { return <SessionListScreen />; }
