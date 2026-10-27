/* Export attendance with full-area calendar pickers and shared Ako controls.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

"use client";
import { useRef, useState, type FormEvent, type MouseEvent } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/components/session-context";
import { downloadAttendance, ReportError, LoginRequiredError, type ReportFormat } from "@/lib/attendance-reports-api";
import styles from "./attendance-reports.module.css";

/*
 * Render the attendance reports interface and its associated content.
 */
export default function AttendanceReports() {
  const session = useSession(), router = useRouter();
  const [start, setStart] = useState(""), [end, setEnd] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState(""), [error, setError] = useState("");
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const pending = useRef(false);
  const startInput = useRef<HTMLInputElement>(null), endInput = useRef<HTMLInputElement>(null);
  if (session?.role !== "coordinator") return <p className="msg msg-error" role="alert">You do not have permission</p>;
  /*
   * Focus the requested report form control.
   */
  function focus(field: string) { (field === "start_date" ? startInput : endInput).current?.focus(); }
  /*
   * Open the native date picker from the field or calendar control when supported.
   */
  function openCalendar(event: MouseEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (input.disabled || typeof input.showPicker !== "function") return;
    try {
      input.showPicker();
      // Avoid the native icon toggling a picker that this click already opened.
      event.preventDefault();
    } catch {
      // Browsers without usable showPicker keep their normal date input behavior.
      input.focus();
    }
  }
  /*
   * Update the selected report date and clear obsolete validation feedback.
   */
  function edited() { setErrors({}); setError(""); setMessage(""); }
  /*
   * Download the selected attendance report and release its browser object URL.
   */
  async function download(format: ReportFormat) {
    if (pending.current) return;
    setMessage(""); setError("");
    const fields: Record<string, string> = {};
    if (!start) fields.start_date = "Start date is required";
    if (!end) fields.end_date = "End date is required";
    if (start && end && start > end) fields.end_date = "Start date must be before end date";
    setErrors(fields);
    if (Object.keys(fields).length) { focus(Object.keys(fields)[0]); return; }
    pending.current = true; setBusy(format);
    try {
      const file = await downloadAttendance(start, end, format);
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement("a"); link.href = url; link.download = file.filename;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(/*
     * Compute the next timeout state from its previous value.
     */
    () => URL.revokeObjectURL(url), 1000);
      setMessage(`${format.toUpperCase()} download started.`);
    } catch (reason) {
      if (reason instanceof LoginRequiredError) router.replace("/");
      else if (reason instanceof ReportError && ["start_date", "end_date"].includes(reason.field || "")) {
        setErrors({ [reason.field!]: reason.message }); focus(reason.field!);
      } else setError(reason instanceof ReportError ? reason.message : "The report could not be downloaded. Please try again.");
    } finally { pending.current = false; setBusy(null); }
  }
  /*
   * Validate and submit the attendance reports form, updating its success and error
   * state.
   */
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void download("pdf"); }
  return <>
    <h1>Attendance reports</h1>
    <p className="sub">Save attendance for a date range as PDF or CSV.</p>
    <section className={`card ${styles.panel}`} aria-label="Export attendance">
      <h2>Choose class dates</h2>
      <p>Both dates are included. Only dates with class sessions become report columns.</p>
      <form onSubmit={submit} noValidate aria-busy={Boolean(busy)}>
        <div className={styles.dates}>
          <div className="field"><label className="req" htmlFor="report-start">Start date</label>
            <input ref={startInput} id="report-start" name="start_date" type="date" data-empty={!start} onClick={openCalendar} value={start} required disabled={Boolean(busy)}
              aria-invalid={Boolean(errors.start_date)} aria-describedby={errors.start_date ? "report-start-error" : undefined}
              onChange={/*
     * Handle the change event for this control.
     */
    event => { setStart(event.target.value); edited(); }} />
            {errors.start_date && <p id="report-start-error" className="msg msg-error" role="alert">{errors.start_date}</p>}
          </div>
          <div className="field"><label className="req" htmlFor="report-end">End date</label>
            <input ref={endInput} id="report-end" name="end_date" type="date" data-empty={!end} onClick={openCalendar} value={end} required disabled={Boolean(busy)}
              aria-invalid={Boolean(errors.end_date)} aria-describedby={errors.end_date ? "report-end-error" : undefined}
              onChange={/*
     * Handle the change event for this control.
     */
    event => { setEnd(event.target.value); edited(); }} />
            {errors.end_date && <p id="report-end-error" className="msg msg-error" role="alert">{errors.end_date}</p>}
          </div>
        </div>
        <p className="hint">Includes current learners and anyone with attendance records in this range. Without a Present record, the learner is shown as Absent.</p>
        <div className={styles.actions}>
          <button className="btn" type="submit" disabled={Boolean(busy)}>{busy === "pdf" ? "Preparing PDF…" : "Download PDF"}</button>
          <button className="btn btn-secondary" type="button" disabled={Boolean(busy)} onClick={/*
     * Handle the click event for this control.
     */
    () => void download("csv")}>{busy === "csv" ? "Preparing CSV…" : "Download CSV"}</button>
        </div>
      </form>
      {busy && <p role="status">Preparing your attendance report…</p>}
      {error && <p className="msg msg-error" role="alert">{error}</p>}
      {message && <p className="msg msg-success" role="status">{message}</p>}
    </section>
    <section className={styles.help} aria-label="Report formats"><h2>Report formats</h2>
      <p><strong>PDF:</strong> A4 pages for printing in black and white. Long reports continue across pages.</p>
      <p><strong>CSV:</strong> One row per learner and one column per class date. Open it in a spreadsheet.</p>
    </section>
  </>;
}
