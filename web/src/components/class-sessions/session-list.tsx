/* List dated classes and create or reopen one session per date (US-014).
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClassSession, listClassSessions, startToday, sessionError, LoginRequiredError, ClassSessionError, type SessionList } from "@/lib/class-sessions-api";
import { formatSessionDate } from "@/lib/dates";
import styles from "./class-sessions.module.css";

export default function SessionListScreen() {
  const router = useRouter();
  const [data, setData] = useState<SessionList | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [day, setDay] = useState("");
  const [dateError, setDateError] = useState("");
  const [creating, setCreating] = useState(false);
  const pending = useRef(false);
  const dateInput = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setData(await listClassSessions()); }
    catch (reason) { if (reason instanceof LoginRequiredError) router.replace("/"); else setError(sessionError(reason)); }
    finally { setLoading(false); }
  }, [router]);
  useEffect(() => { void load(); }, [load]);
  async function open(today: boolean) {
    if (pending.current) return;
    setDateError(""); setError("");
    if (!today && (!day || (data && day > data.today))) {
      setDateError(!day ? "Class date is required" : "Date cannot be in the future"); dateInput.current?.focus(); return;
    }
    pending.current = true; setBusy(true);
    try {
      const result = today ? await startToday() : await createClassSession(day);
      router.push(`/sessions/${result.id}`);
    } catch (reason) {
      if (reason instanceof LoginRequiredError) router.replace("/");
      else if (reason instanceof ClassSessionError && reason.field === "session_date") { setDateError(reason.message); dateInput.current?.focus(); }
      else setError(sessionError(reason));
    } finally { pending.current = false; setBusy(false); }
  }
  return <>
    <h1>Class sessions</h1>
    <p className="sub">Open a class, choose its lesson and record attendance.</p>
    <div className={`row no-print ${styles.toolbar}`}>
      <button className="btn" disabled={busy} onClick={() => void open(true)}>{busy ? "Opening class…" : "Start today's class"}</button>
      <button className="btn btn-secondary" disabled={busy} onClick={() => { setCreating(value => !value); setDateError(""); }}>New class session</button>
      <button className="btn btn-secondary" disabled={loading || busy} onClick={() => void load()}>Refresh</button>
    </div>
    {creating && <form className={`card no-print ${styles.form}`} noValidate onSubmit={event => { event.preventDefault(); void open(false); }}>
      <h2>Create a class session</h2>
      <div className="field"><label className="req" htmlFor="class-date">Class date</label>
        <input ref={dateInput} id="class-date" name="session_date" type="date" value={day} max={data?.today} required disabled={busy}
          aria-invalid={Boolean(dateError)} aria-describedby={dateError ? "class-date-error" : "class-date-hint"}
          onChange={event => { setDay(event.target.value); setDateError(""); }} />
        <p className="hint" id="class-date-hint">Choose today or an earlier date. Existing classes open without duplication.</p>
        {dateError && <p className="msg msg-error" role="alert" id="class-date-error">{dateError}</p>}
      </div>
      <div className="row"><button className="btn" disabled={busy} type="submit">Create or open class</button>
        <button className="btn btn-secondary" disabled={busy} type="button" onClick={() => setCreating(false)}>Cancel</button></div>
    </form>}
    {error && <p className="msg msg-error" role="alert">{error}</p>}
    {loading && <p role="status">Loading class sessions…</p>}
    {!loading && data && <>
      {!data.sessions.length ? <p className="msg msg-info" role="status">No class sessions yet. Start today's class to begin.</p> :
        <div className={styles.table} role="region" aria-label="Class sessions" tabIndex={0}><table className="data">
          <thead><tr><th scope="col">Date</th><th scope="col">Lesson</th><th scope="col">Attendance</th><th scope="col" className="no-print">Actions</th></tr></thead>
          <tbody>{data.sessions.map(session => <tr key={session.id}>
            <td><Link href={`/sessions/${session.id}`}><time dateTime={session.session_date}>{formatSessionDate(session.session_date)}</time></Link></td>
            <td>{session.lesson_unavailable ? "Lesson unavailable" : session.lesson_title || "No lesson linked"}</td>
            <td>{session.present_count} present</td>
            <td className="no-print"><div className={styles.actions}><Link className="btn btn-secondary" href={`/sessions/${session.id}`}>Open class</Link>
              <Link className="btn btn-secondary" href={`/sessions/${session.id}/attendance`}>Attendance</Link></div></td>
          </tr>)}</tbody>
        </table></div>}
    </>}
  </>;
}
