/* Download attendance reports with the HttpOnly staff session and useful errors.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import { LoginRequiredError, RequestFailedError } from "./api";
export { LoginRequiredError } from "./api";
export type ReportFormat = "pdf" | "csv";
export class ReportError extends Error {
  constructor(message: string, public field?: string, public status?: number) { super(message); }
}
export async function downloadAttendance(start: string, end: string, format: ReportFormat): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch("/api/staff/access/reports/attendance", {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", cache: "no-store",
      body: JSON.stringify({ start_date: start, end_date: end, format }),
    });
  } catch { throw new RequestFailedError(); }
  if (response.status === 401) throw new LoginRequiredError();
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    const detail = result?.detail;
    const message = response.status === 403 ? "You do not have permission"
      : response.status === 404 ? "No classes found for these dates"
      : response.status === 422 && typeof detail?.message === "string" ? detail.message
      : "The report could not be downloaded. Please try again.";
    throw new ReportError(message, typeof detail?.field === "string" ? detail.field : undefined, response.status);
  }
  const type = response.headers.get("content-type") || "";
  if (!type.startsWith(format === "pdf" ? "application/pdf" : "text/csv")) throw new ReportError("The report could not be downloaded. Please try again.");
  const blob = await response.blob();
  if (!blob.size) throw new ReportError("The report could not be downloaded. Please try again.");
  return { blob, filename: `ako-attendance-${start}-${end}.${format}` };
}
