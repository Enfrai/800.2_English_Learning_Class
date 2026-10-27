/* Open a dated classroom and its lesson and attendance actions (US-014).
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import SessionDetailScreen from "@/components/class-sessions/session-detail";
export const metadata = { title: "Class session" };
/*
 * Render the class-session detail route.
 */
export default async function Page({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <SessionDetailScreen sessionId={sessionId} />;
}
