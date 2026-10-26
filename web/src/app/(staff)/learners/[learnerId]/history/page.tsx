/* Open individual attendance history in the shared Ako staff layout.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import AttendanceHistoryScreen from "@/components/attendance-history/attendance-history-screen";
export const metadata = { title: "Learner attendance history" };
export default async function HistoryPage({ params }: { params: Promise<{ learnerId: string }> }) {
  const { learnerId } = await params;
  return <AttendanceHistoryScreen learnerId={learnerId} />;
}
