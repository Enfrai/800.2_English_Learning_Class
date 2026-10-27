/* Attendance (sign-in) page route for one class session (US-004).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

import type { Metadata } from "next";
import AttendanceScreen from "@/components/attendance/attendance-screen";

export const metadata: Metadata = { title: "Attendance" };

/*
 * Render the attendance page interface and its associated content.
 */
export default async function AttendancePage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <AttendanceScreen sessionId={sessionId} />;
}
