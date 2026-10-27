/* Manage staff QR windows and prepare an A4 check-in print sheet.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import { apiRequest, LoginRequiredError } from "./api";
export { LoginRequiredError } from "./api";
export type CheckinWindow = {
  state: "not-open" | "open" | "closed" | "expired" | "unavailable";
  session_date: string; can_open: boolean;
  opened_at: string | null; expires_at: string | null;
  sign_in_url: string | null; qr_svg: string | null;
};
export class CheckinError extends Error {}
/*
 * Send a staff request for a classroom check-in window and translate API failures.
 */
async function windowRequest(id: string, method: "GET" | "POST" | "DELETE"): Promise<CheckinWindow> {
  const result = await apiRequest(`/api/access/sessions/${encodeURIComponent(id)}/check-in`, { method });
  if (result.status === 403) throw new CheckinError("You do not have permission");
  if (result.status === 404) throw new CheckinError("Class session not found");
  if (result.status === 409) throw new CheckinError(result.message || "Check-in cannot open for this class");
  if (result.status !== 200) throw new CheckinError("Check-in could not be updated. Please try again.");
  return result.body as CheckinWindow;
}
/*
 * Read the classroom check-in window state and QR display data.
 */
export const getWindow = (id: string) => windowRequest(id, "GET");
/*
 * Open or reuse the classroom check-in window.
 */
export const openWindow = (id: string) => windowRequest(id, "POST");
/*
 * Close the classroom check-in window through the staff API.
 */
export const closeWindow = (id: string) => windowRequest(id, "DELETE");
/*
 * Return the safe check-in error message for display.
 */
export function checkinError(reason: unknown): string { return reason instanceof CheckinError ? reason.message : "Check-in could not be updated. Please try again."; }
/*
 * Escape text before embedding it in the printable check-in HTML.
 */
const escape = (value: string) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
/*
 * Generate the printable classroom QR document from the open window.
 */
export function printDocument(window: CheckinWindow): string {
  if (window.state !== "open" || !window.qr_svg || !window.sign_in_url) throw new CheckinError("Check-in is closed");
  const image = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(window.qr_svg);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Ako class sign-in</title><style>
    @page { size: A4; margin: 20mm; } body { font: 18px/1.5 Arial,sans-serif; color: #000; background:#fff; text-align:center; }
    img { display:block; width:110mm; height:110mm; margin:12mm auto; background:#fff; } p { overflow-wrap:anywhere; } a {color:#000;}
    </style></head><body><h1>Ako class sign-in</h1><p>Class date: ${escape(window.session_date)}</p>
    <img src="${image}" alt="Class sign-in QR code"><p>Scan this code and enter your name.</p><p><a href="${escape(window.sign_in_url)}">${escape(window.sign_in_url)}</a></p>
    <p>This code works only while check-in is open.</p></body></html>`;
}
/*
 * Open the QR print document and coordinate browser printing and cleanup.
 */
export function printWindow(window: CheckinWindow): void {
  const frame = document.createElement("iframe");
  frame.title = "Print class sign-in QR code";
  Object.assign(frame.style, { position: "fixed", width: "1px", height: "1px", opacity: "0", border: "0", pointerEvents: "none" });
  frame.srcdoc = printDocument(window);
  frame.onload = /*
     * Update frame.onload for the checkin management api workflow.
     */
    async () => {
    const view = frame.contentWindow;
    if (!view) return;
    await Promise.all(Array.from(view.document.images).map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    image => image.decode().catch(/*
     * Handle an asynchronous failure using the workflow’s error state.
     */
    () => undefined)));
    view.addEventListener("afterprint", /*
     * Handle the registered browser event for the current workflow.
     */
    () => frame.remove(), { once: true });
    view.focus(); view.print();
    globalThis.setTimeout(/*
     * Compute the next timeout state from its previous value.
     */
    () => frame.remove(), 60000);
  };
  document.body.appendChild(frame);
}
