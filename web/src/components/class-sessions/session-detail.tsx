/* Manage classroom lessons, attendance and printable QR check-in.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

"use client";
import Link from "next/link";
import CheckInPanel from "@/components/check-in/check-in-panel";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { deleteClassSession, getClassSession, linkClassLesson, sessionError, LoginRequiredError, type SessionDetails } from "@/lib/class-sessions-api";
import { listLessons, messageFor, type Lesson } from "@/lib/lessons-api";
import { formatSessionDate } from "@/lib/dates";
import styles from "./class-sessions.module.css";

/*
 * Render the session detail screen interface and its associated content.
 */
export default function SessionDetailScreen({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<SessionDetails | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [lessonError, setLessonError] = useState("");
  const [lessonsReady, setLessonsReady] = useState(false);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const pending = useRef(false);
  const load = useCallback(/*
     * Run the memoized load operation for the current dependencies.
     */
    async () => {
    setError("");
    try { const row = await getClassSession(sessionId); setSession(row); setSelected(row.lesson_id || ""); }
    catch (reason) { if (reason instanceof LoginRequiredError) router.replace("/"); else setError(sessionError(reason)); }
  }, [router, sessionId]);
  const loadLessons = useCallback(/*
     * Run the memoized load lessons operation for the current dependencies.
     */
    async () => {
    setLessonError("");
    try { setLessons(await listLessons()); setLessonsReady(true); }
    catch (reason) { if (reason instanceof LoginRequiredError) router.replace("/"); else setLessonError(messageFor(reason)); }
  }, [router]);
  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => { void load(); void loadLessons(); }, [load, loadLessons]);
  /*
   * Validate and submit the session detail form, updating its success and error state.
   */
  async function save() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try { const updated = await linkClassLesson(sessionId, selected || null); setSession(/*
     * Compute the next session state from its previous value.
     */
    current => current ? { ...current, ...updated } : current); setNotice("Lesson saved for this class."); }
    catch (reason) { if (reason instanceof LoginRequiredError) router.replace("/"); else setError(sessionError(reason)); }
    finally { pending.current = false; setBusy(false); }
  }
  /*
   * Apply the confirmed class session deletion and update the current view.
   */
  async function remove() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await deleteClassSession(sessionId); router.push("/sessions"); }
    catch (reason) { if (reason instanceof LoginRequiredError) router.replace("/"); else setError(sessionError(reason)); }
    finally { pending.current = false; setBusy(false); }
  }
  if (!session) return <><h1>Class session</h1>{error ? <><p className="msg msg-error" role="alert">{error}</p><button className="btn btn-secondary" onClick={/*
     * Handle the click event for this control.
     */
    () => void load()}>Try again</button></> : <p role="status">Loading class…</p>}<p><Link href="/sessions">Back to class sessions</Link></p></>;
  return <>
    <h1 className={styles.heading}>Class session</h1>
    <p className="sub"><time dateTime={session.session_date}>{formatSessionDate(session.session_date)}</time></p>
    <div className={`row no-print ${styles.toolbar}`}><Link className="btn btn-secondary" href="/sessions">Back to class sessions</Link>
      <Link className="btn" href={`/sessions/${session.id}/attendance`}>Attendance</Link>
      <button className="btn btn-danger" disabled={busy || !session.can_delete} onClick={/*
     * Handle the click event for this control.
     */
    () => setConfirm(true)}>Delete session</button></div>
    <p>{session.present_count} present · {session.attendance_count} attendance records</p>
    {!session.can_delete && <p className="msg msg-info">This session has attendance and cannot be deleted</p>}
    {session.session_date < session.today && <p className="msg msg-info">Only a coordinator can correct past attendance</p>}
    <CheckInPanel sessionId={session.id} />
    <section className={styles.lesson} aria-labelledby="class-lesson-heading"><h2 id="class-lesson-heading">Class lesson</h2>
      <p>{session.lesson_unavailable ? "Lesson unavailable" : session.lesson_title || "No lesson linked"}</p>
      {lessonError && <p className="msg msg-warning" role="alert">{lessonError} <button className="btn btn-secondary" onClick={/*
     * Handle the click event for this control.
     */
    () => void loadLessons()}>Retry lessons</button></p>}
      {lessonsReady && <form onSubmit={/*
     * Handle the submit event for this control.
     */
    event => { event.preventDefault(); void save(); }} aria-busy={busy}>
        <div className="field"><label htmlFor="class-lesson">Lesson</label>
          <select id="class-lesson" value={selected} disabled={busy} onChange={/*
     * Handle the change event for this control.
     */
    event => { setSelected(event.target.value); setNotice(""); }}>
            <option value="">No lesson linked</option>
            {selected && !lessons.some(/*
     * Check whether any collection entry matches this condition.
     */
    lesson => lesson.id === selected) && <option value={selected}>Lesson unavailable</option>}
            {lessons.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    lesson => <option key={lesson.id} value={lesson.id}>{lesson.title}</option>)}
          </select><p className="hint">Choose a saved lesson. Its content and date stay unchanged.</p></div>
        <button type="submit" className="btn" disabled={busy}>Save lesson</button>
      </form>}
      {notice && <p className="msg msg-success" role="status">{notice}</p>}
    </section>
    {confirm && <section className={`card no-print ${styles.confirm}`} aria-labelledby="delete-class-heading">
      <h2 id="delete-class-heading">Delete session?</h2><p>{formatSessionDate(session.session_date)}</p>
      <p>This removes the class session. Its linked lesson stays in the library.</p>
      <div className="row"><button className="btn btn-danger" disabled={busy} onClick={/*
     * Handle the click event for this control.
     */
    () => void remove()}>Confirm deletion</button>
        <button className="btn btn-secondary" disabled={busy} onClick={/*
     * Handle the click event for this control.
     */
    () => setConfirm(false)}>Cancel deletion</button></div>
    </section>}
    {error && <p className="msg msg-error" role="alert">{error}</p>}
  </>;
}
