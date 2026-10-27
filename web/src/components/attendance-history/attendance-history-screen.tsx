/* Show read-only learner history, inclusive filters, totals and safe error states.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import { useRouter } from "next/navigation";
import { getAttendanceHistory, HistoryError, LoginRequiredError, type AttendanceHistory } from "@/lib/attendance-history-api";
import styles from "./attendance-history.module.css";

/*
 * Render the attendance history screen interface and its associated content.
 */
export default function AttendanceHistoryScreen({ learnerId }: { learnerId: string }) {
  const router = useRouter();
  const [data, setData] = useState<AttendanceHistory | null>(null);
  const [start, setStart] = useState(""), [end, setEnd] = useState("");
  const [applied, setApplied] = useState({ start: "", end: "" });
  const [busy, setBusy] = useState(true), [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");
  const endInput = useRef<HTMLInputElement>(null), generation = useRef(0);
  const load = useCallback(/*
     * Run the memoized load operation for the current dependencies.
     */
    async (from: string, to: string) => {
    const current = ++generation.current;
    setBusy(true); setError(""); setData(null);
    try {
      const result = await getAttendanceHistory(learnerId, from, to);
      if (current === generation.current) { setData(result); setApplied({ start: from, end: to }); }
    } catch (reason) {
      if (current !== generation.current) return;
      if (reason instanceof LoginRequiredError) router.replace("/");
      else if (reason instanceof HistoryError && reason.field) { setFieldError(reason.message); endInput.current?.focus(); }
      else setError(reason instanceof HistoryError ? reason.message : "Attendance history could not be loaded. Please try again.");
    } finally { if (current === generation.current) setBusy(false); }
  }, [learnerId, router]);
  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    setStart(""); setEnd(""); setFieldError(""); void load("", "");
    /*
     * Release resources installed by the enclosing component effect.
     */
    return () => { generation.current++; };
  }, [load]);
  /*
   * Open the native date picker from the field or calendar control when supported.
   */
  function openCalendar(event: MouseEvent<HTMLInputElement>) {
    if (typeof event.currentTarget.showPicker !== "function") return;
    try { event.currentTarget.showPicker(); event.preventDefault(); } catch { event.currentTarget.focus(); }
  }
  /*
   * Validate and submit the attendance history screen form, updating its success and
   * error state.
   */
  function submit(event: FormEvent) {
    event.preventDefault();
    if (start && end && start > end) { setFieldError("Start date must be before end date"); endInput.current?.focus(); return; }
    setFieldError(""); void load(start, end);
  }
  /*
   * Clear attendance-history filters and reload the complete learner history.
   */
  function reset() { setStart(""); setEnd(""); setFieldError(""); void load("", ""); }
  return <>
    <Link className="btn btn-secondary no-print" href="/learners">Back to learners</Link>
    <h1>Attendance history</h1>
    {data && <h2 className={styles.name}>{data.learner.name}</h2>}
    <p className="sub">Read-only history. Past classes and closed classes today are included.</p>
    <section className={`card no-print ${styles.panel}`} aria-label="Filter attendance history">
      <h2>Choose class dates</h2><p>Both dates are included. Leave either date blank for no limit.</p>
      <form onSubmit={submit} noValidate aria-busy={busy}>
        <div className={styles.dates}>
          <div className="field"><label htmlFor="history-start">Start date</label>
            <input id="history-start" type="date" value={start} data-empty={!start} onClick={openCalendar} disabled={busy}
              onChange={/*
     * Handle the change event for this control.
     */
    e => { setStart(e.target.value); setFieldError(""); }} /></div>
          <div className="field"><label htmlFor="history-end">End date</label>
            <input ref={endInput} id="history-end" type="date" value={end} data-empty={!end} onClick={openCalendar} disabled={busy}
              aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? "history-date-error" : undefined}
              onChange={/*
     * Handle the change event for this control.
     */
    e => { setEnd(e.target.value); setFieldError(""); }} /></div>
        </div>
        {fieldError && <p id="history-date-error" className="msg msg-error" role="alert">{fieldError}</p>}
        <div className="row"><button type="submit" className="btn" disabled={busy}>Apply dates</button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={reset}>Reset dates</button></div>
      </form>
    </section>
    {busy && <p role="status">Loading attendance history…</p>}
    {error && <div className="msg msg-error" role="alert"><p>{error}</p>{!["Learner not found", "You do not have permission"].includes(error) &&
      <button className="btn btn-secondary" type="button" onClick={/*
     * Handle the click event for this control.
     */
    () => void load(start, end)}>Try again</button>}</div>}
    {!busy && data && <section aria-label="Learner attendance results" aria-live="polite">
      <p className="msg msg-info" role="status">Present {data.present_count} of {data.total_count}</p>
      <p>{applied.start || "First class"} to {applied.end || "Latest completed class"}</p>
      {!data.has_records ? <p>No attendance recorded yet</p> : !data.sessions.length ? <p>No class sessions in this date range</p> :
        <table className={`data ${styles.table}`}><caption>Class attendance, newest first</caption>
          <thead><tr><th scope="col">Class date</th><th scope="col">Attendance</th></tr></thead>
          <tbody>{data.sessions.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    row => <tr key={row.session_id}><th scope="row">{row.session_date}</th><td>{row.status}</td></tr>)}</tbody>
        </table>}
      <p className="hint">Missing Present records count as Absent after the first attendance record.</p>
      <p className="hint">Classes before the learner joined are excluded unless an attendance record exists.</p>
    </section>}
  </>;
}
