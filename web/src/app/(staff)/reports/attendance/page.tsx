/* Open the coordinator attendance report page in the shared Ako layout.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import AttendanceReports from "@/components/attendance-reports/attendance-reports";

export const metadata = { title: "Attendance reports" };
/*
 * Render the attendance reports page interface and its associated content.
 */
export default function AttendanceReportsPage() { return <AttendanceReports />; }
