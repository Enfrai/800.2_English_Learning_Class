/* Read learner attendance history through the protected cookie adapter.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import { apiRequest, RequestFailedError } from "./api";
export { LoginRequiredError } from "./api";
export type AttendanceHistory = {
  learner: { id: string; name: string };
  sessions: { session_id: string; session_date: string; status: "Present" | "Absent" }[];
  present_count: number; total_count: number; has_records: boolean;
  start_date: string | null; end_date: string | null;
};
export class HistoryError extends Error {
  constructor(message: string, readonly status: number, readonly field?: string) { super(message); }
}
export async function getAttendanceHistory(id: string, start = "", end = ""): Promise<AttendanceHistory> {
  const query = new URLSearchParams();
  if (start) query.set("start_date", start);
  if (end) query.set("end_date", end);
  const { status, body, detail } = await apiRequest(`/api/access/learners/${encodeURIComponent(id)}/attendance-history${query.size ? "?" + query : ""}`);
  if (status === 403) throw new HistoryError("You do not have permission", status);
  if (status === 404) throw new HistoryError("Learner not found", status);
  if (status === 422 && detail?.field === "end_date") throw new HistoryError("Start date must be before end date", status, "end_date");
  if (status !== 200) throw new RequestFailedError();
  const value = body as AttendanceHistory;
  if (!value?.learner || value.learner.id !== id || typeof value.learner.name !== "string"
      || !Array.isArray(value.sessions) || typeof value.has_records !== "boolean"
      || value.total_count !== value.sessions.length
      || !value.sessions.every(row => typeof row.session_id === "string" && /^\d{4}-\d{2}-\d{2}$/.test(row.session_date) && ["Present", "Absent"].includes(row.status))
      || value.present_count !== value.sessions.filter(row => row.status === "Present").length) throw new RequestFailedError();
  return value;
}
