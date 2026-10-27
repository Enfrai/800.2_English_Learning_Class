/* Attendance (sign-in) page for one class session (UI design document 6.6, US-004),
 * and correcting past classes, with live QR attendance refresh (US-011/015).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 * Updated: Pei Wu, 25 Oct 2026 (US-015 correction view and change history)
 * Updated: Shuohui Liu, 26 Oct 2026
 */

"use client";

import Link from "next/link";
import SessionLesson from "@/components/materials/session-lesson";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { type FieldErrors, TextField, checkNames } from "@/components/learners/learner-form";
import { useSession } from "@/components/session-context";
import { LoginRequiredError } from "@/lib/api";
import {
  AlreadySignedInError,
  type AttendanceRecord,
  type Correction,
  NotFoundError,
  PastSessionError,
  SessionNotPastError,
  addAndMarkPresent,
  correctAttendance,
  getAttendance,
  getCorrections,
  markPresent,
  unmarkPresent,
} from "@/lib/attendance-api";
import { type Learner, LearnerFieldError, listLearners } from "@/lib/learners-api";
import { formatSessionDate } from "@/lib/dates";

type LoadState = "loading" | "ready" | "login-required" | "not-found" | "failed";
type Message = { kind: "info" | "warning" | "error" | "success"; text: string };
type ListedLearner = Pick<Learner, "id" | "first_name" | "family_name" | "first_language">;
/** "class": the class is today or later (6.6); "correct": a coordinator on a
 * past class (6.16); "view": anyone else on a past class. */
type Mode = "class" | "correct" | "view";

// Message catalogue, UI design document section 7.
const PAST_ATTENDANCE_LOCKED = "Only a coordinator can correct past attendance";
const CHANGE_FAILED = "The change could not be saved. Please try again.";
const CORRECTION_NOTICE = "You are correcting a past class. Every change is logged with your name and the time";
const HISTORY_FAILED = "The change history could not be loaded. Please try again.";

/*
 * Combine the learner’s given and family names for display.
 */
function fullName(learner: Pick<Learner, "first_name" | "family_name">): string {
  return `${learner.first_name} ${learner.family_name}`;
}

/*
 * Compare learners by family name and then given name.
 */
function byFamilyThenFirstName(a: ListedLearner, b: ListedLearner): number {
  return (
    a.family_name.localeCompare(b.family_name, undefined, { sensitivity: "base" }) ||
    a.first_name.localeCompare(b.first_name, undefined, { sensitivity: "base" })
  );
}

/*
 * Format an attendance timestamp for the club interface.
 */
function formatTime(isoTime: string): string {
  return new Date(isoTime).toLocaleTimeString("en-NZ", { hour: "numeric", minute: "2-digit" });
}

/*
 * Format a correction timestamp for the change-history interface.
 */
function formatChangeTime(isoTime: string): string {
  return new Date(isoTime).toLocaleString("en-NZ", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/*
 * Return the attendance-status label shown to staff.
 */
function statusLabel(status: string): string {
  return status === "present" ? "Present" : "Absent";
}

/*
 * Render the message box interface and its associated content.
 */
function MessageBox({ message }: { message: Message | null }) {
  if (!message) return null;
  const urgent = message.kind === "error" || message.kind === "warning";
  return (
    <div className={`msg msg-${message.kind}`} role={urgent ? "alert" : "status"}>
      {message.text}
    </div>
  );
}

/*
 * Render the attendance screen interface and its associated content.
 */
export default function AttendanceScreen({ sessionId }: { sessionId: string }) {
  // The server decides who may correct; the role only chooses the view.
  const isCoordinator = useSession()?.role === "coordinator";
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [learners, setLearners] = useState<ListedLearner[]>([]);
  const [records, setRecords] = useState<Map<string, AttendanceRecord>>(new Map());
  const [presentCount, setPresentCount] = useState(0);
  const [sessionDate, setSessionDate] = useState("");
  const [editable, setEditable] = useState(false);
  const [corrected, setCorrected] = useState<Set<string>>(new Set());
  // Bumped after each correction so the change history loads again.
  const [historyVersion, setHistoryVersion] = useState(0);
  // Learners whose tick is being saved, with the state the teacher chose.
  const [pending, setPending] = useState<Map<string, boolean>>(new Map());
  // Messages about one learner are shown in that learner's row (UI kit rule 3).
  const [rowMessages, setRowMessages] = useState<Map<string, Message>>(new Map());

  const loadVersion = useRef(0), writes = useRef(0), polling = useRef(false);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const load = useCallback(/*
     * Run the memoized load operation for the current dependencies.
     */
    async (silent = false) => {
    if (silent && (writes.current || polling.current)) return;
    if (silent) polling.current = true;
    const version = ++loadVersion.current;
    try {
      const [classList, attendance] = await Promise.all([
        listLearners(),
        getAttendance(sessionId),
      ]);
      if (version !== loadVersion.current || (silent && writes.current)) return;
      setRefreshFailed(false);
      setLearners(classList);
      setRecords(new Map(attendance.records.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    (record) => [record.learner_id, record])));
      setPresentCount(attendance.present_count);
      setSessionDate(attendance.session_date);
      setEditable(attendance.editable);
      setCorrected(new Set(attendance.corrected_learner_ids));
      if (!silent) setHistoryVersion(/*
     * Compute the next history version state from its previous value.
     */
    (version) => version + 1);
      setLoadState("ready");
    } catch (error) {
      if (version !== loadVersion.current) return;
      if (silent && !(error instanceof LoginRequiredError) && !(error instanceof NotFoundError)) { setRefreshFailed(true); return; }
      if (error instanceof LoginRequiredError) setLoadState("login-required");
      else if (error instanceof NotFoundError) setLoadState("not-found");
      else setLoadState("failed");
    } finally { if (silent) polling.current = false; }
  }, [sessionId]);

  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    void load();
    /*
     * Release resources installed by the enclosing component effect.
     */
    return () => { loadVersion.current++; };
  }, [load]);
  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    if (!editable || loadState !== "ready") return;
    const timer = window.setInterval(/*
     * Compute the next interval state from its previous value.
     */
    () => { if (!document.hidden) void load(true); }, 3000);
    /*
     * Release resources installed by the enclosing component effect.
     */
    return () => clearInterval(timer);
  }, [load, editable, loadState]);

  /*
   * Update the local attendance record for the selected learner.
   */
  function setRecord(learnerId: string, record: AttendanceRecord | null) {
    loadVersion.current++;
    setRecords(/*
     * Compute the next records state from its previous value.
     */
    (current) => {
      const next = new Map(current);
      if (record) next.set(learnerId, record);
      else next.delete(learnerId);
      return next;
    });
  }

  /*
   * Set the attendance message for the selected learner row.
   */
  function setRowMessage(learnerId: string, message: Message | null) {
    setRowMessages(/*
     * Compute the next row messages state from its previous value.
     */
    (current) => {
      const next = new Map(current);
      if (message) next.set(learnerId, message);
      else next.delete(learnerId);
      return next;
    });
  }

  /*
   * Disable ordinary attendance editing after the class becomes historical.
   */
  function lockPastSession() {
    setEditable(false);
  }

  const mode: Mode = editable ? "class" : isCoordinator ? "correct" : "view";

  /*
   * Apply the requested attendance change while handling duplicates and permission
   * errors.
   */
  async function toggle(learner: ListedLearner, present: boolean) {
    if (pending.has(learner.id)) return;
    writes.current++; loadVersion.current++;
    setPending(/*
     * Compute the next pending state from its previous value.
     */
    (current) => new Map(current).set(learner.id, present));
    setRowMessage(learner.id, null);
    try {
      if (mode === "correct") {
        const change = await correctAttendance(sessionId, learner.id, present);
        // An unticked learner keeps an absent record; the list shows present ones.
        setRecord(learner.id, change.attendance?.status === "present" ? change.attendance : null);
        setPresentCount(change.present_count);
        setCorrected(/*
     * Compute the next corrected state from its previous value.
     */
    (current) => new Set(current).add(learner.id));
        setHistoryVersion(/*
     * Compute the next history version state from its previous value.
     */
    (version) => version + 1);
      } else {
        const change = present
          ? await markPresent(sessionId, learner.id)
          : await unmarkPresent(sessionId, learner.id);
        setRecord(learner.id, change.attendance);
        setPresentCount(change.present_count);
      }
    } catch (error) {
      if (error instanceof AlreadySignedInError) {
        setRowMessage(learner.id, { kind: "info", text: error.message });
        await load();
      } else if (error instanceof PastSessionError) {
        if (mode === "correct") setRowMessage(learner.id, { kind: "error", text: error.message });
        else lockPastSession();
      } else if (error instanceof NotFoundError || error instanceof SessionNotPastError) await load();
      else if (error instanceof LoginRequiredError) setLoadState("login-required");
      else setRowMessage(learner.id, { kind: "error", text: CHANGE_FAILED });
    } finally {
      writes.current--;
      setPending(/*
     * Compute the next pending state from its previous value.
     */
    (current) => {
        const next = new Map(current);
        next.delete(learner.id);
        return next;
      });
    }
  }

  /*
   * Add the returned learner and attendance result to the current class view.
   */
  function handleAdded(learner: ListedLearner, record: AttendanceRecord | null, count: number) {
    setLearners(/*
     * Compute the next learners state from its previous value.
     */
    (current) =>
      current.some(/*
     * Check whether any collection entry matches this condition.
     */
    (listed) => listed.id === learner.id)
        ? current
        : [...current, learner].sort(byFamilyThenFirstName),
    );
    setRecord(learner.id, record);
    setPresentCount(count);
  }

  if (loadState === "login-required") {
    return (
      <>
        <h1>Attendance</h1>
      <p className="no-print"><Link href={`/sessions/${sessionId}`}>Back to class session</Link></p>
        <div className="msg msg-error" role="alert">
          Please log in to take attendance. <a href="/">Log in</a>
        </div>
      </>
    );
  }
  if (loadState === "not-found") {
    return (
      <>
        <h1>Attendance</h1>
      <p className="no-print"><Link href={`/sessions/${sessionId}`}>Back to class session</Link></p>
        <div className="msg msg-error" role="alert">
          Class session not found
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Attendance</h1>
      <p className="no-print"><Link href={`/sessions/${sessionId}`}>Back to class session</Link></p>
      <SessionLesson sessionId={sessionId} />
      {refreshFailed && <p className="msg msg-warning" role="status">Live attendance could not refresh. Retrying…</p>}
      {loadState === "loading" && <p role="status">Loading the class list…</p>}
      {loadState === "failed" && (
        <div className="msg msg-error" role="alert">
          The class list could not be loaded. Please try again.{" "}
          <button type="button" className="btn btn-secondary" onClick={/*
     * Handle the click event for this control.
     */
    () => void load()}>
            Try again
          </button>
        </div>
      )}
      {loadState === "ready" && (
        <>
          <p className="sub">{formatSessionDate(sessionDate)}</p>
          <div className="row">
            <span className="stat" role="status" aria-live="polite">
              Present {presentCount} of {learners.length}
            </span>
            <button type="button" className="btn btn-secondary no-print" onClick={/*
     * Handle the click event for this control.
     */
    () => window.print()}>
              Print this list
            </button>
            <Link className="btn btn-secondary no-print" href={`/sessions/${sessionId}#qr-heading`}>
              Manage QR check-in
            </Link>
          </div>
          {mode === "correct" && <div className="msg msg-info">{CORRECTION_NOTICE}</div>}
          {mode === "view" && (
            <div className="msg msg-warning" role="alert">
              {PAST_ATTENDANCE_LOCKED}
            </div>
          )}
          <ClassList
            learners={learners}
            records={records}
            corrected={corrected}
            pending={pending}
            rowMessages={rowMessages}
            tickBoxes={mode !== "view"}
            onToggle={/*
     * Handle the toggle event for this control.
     */
    (learner, present) => void toggle(learner, present)}
          />
          {mode === "correct" && <ChangeHistory sessionId={sessionId} version={historyVersion} />}
          {mode === "class" && (
            <AddAndMarkForm
              sessionId={sessionId}
              onAdded={handleAdded}
              onPastSession={lockPastSession}
              onLoginRequired={/*
     * Handle the login required event for this control.
     */
    () => setLoadState("login-required")}
            />
          )}
        </>
      )}
    </>
  );
}

/*
 * Render the class list interface and its associated content.
 */
function ClassList({
  learners,
  records,
  corrected,
  pending,
  rowMessages,
  tickBoxes,
  onToggle,
}: {
  learners: ListedLearner[];
  records: Map<string, AttendanceRecord>;
  corrected: Set<string>;
  pending: Map<string, boolean>;
  rowMessages: Map<string, Message>;
  /** False shows the list without tick boxes (a teacher on a past class). */
  tickBoxes: boolean;
  onToggle: (learner: ListedLearner, present: boolean) => void;
}) {
  if (learners.length === 0) {
    return <div className="msg msg-info">No learners yet. Add a learner below to mark them present.</div>;
  }
  return (
    <table className="data" style={{ marginTop: "var(--space-4)" }}>
      <thead>
        <tr>
          {tickBoxes && <th scope="col">Present</th>}
          <th scope="col">Name</th>
          <th scope="col">First language</th>
          <th scope="col">Time</th>
        </tr>
      </thead>
      <tbody>
        {learners.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    (learner) => {
          const record = records.get(learner.id);
          const checkboxId = `present-${learner.id}`;
          return (
            <tr key={learner.id}>
              {tickBoxes && (
                <td>
                  <div className="check">
                    <input
                      id={checkboxId}
                      type="checkbox"
                      // Show the teacher's choice at once; it reverts if saving fails.
                      checked={pending.get(learner.id) ?? Boolean(record)}
                      aria-busy={pending.has(learner.id)}
                      onChange={/*
     * Handle the change event for this control.
     */
    (event) => onToggle(learner, event.target.checked)}
                    />
                  </div>
                </td>
              )}
              <td style={{ overflowWrap: "anywhere" }}>
                {/* Clicking the name ticks the box; it also names the box for screen readers. */}
                {tickBoxes ? <label htmlFor={checkboxId}>{fullName(learner)}</label> : fullName(learner)}
              </td>
              <td>{learner.first_language ?? "–"}</td>
              <td>
                {record && (
                  <>
                    <span className="badge badge-present">Present</span> {formatTime(record.recorded_at)}
                  </>
                )}
                {corrected.has(learner.id) && (
                  <>
                    {" "}
                    <span className="badge badge-corrected">Corrected</span>
                  </>
                )}
                <MessageBox message={rowMessages.get(learner.id) ?? null} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/*
 * Render the change history interface and its associated content.
 */
function ChangeHistory({ sessionId, version }: { sessionId: string; version: number }) {
  const [history, setHistory] = useState<Correction[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(/*
     * Synchronize the component with its current dependencies and manage effect
     * resources.
     */
    () => {
    let current = true;
    getCorrections(sessionId).then(
      /*
       * Apply the completed asynchronous result to the component’s data or state.
       */
      (entries) => {
        if (!current) return;
        setHistory(entries);
        setFailed(false);
      },
      /*
       * Apply the completed asynchronous result to the component’s data or state.
       */
      () => {
        if (current) setFailed(true);
      },
    );
    /*
     * Release resources installed by the enclosing component effect.
     */
    return () => {
      current = false;
    };
  }, [sessionId, version]);

  return (
    <section aria-labelledby="change-history-title">
      <h2 id="change-history-title">Change history</h2>
      {failed && (
        <div className="msg msg-error" role="alert">
          {HISTORY_FAILED}
        </div>
      )}
      {!failed && history === null && <p role="status">Loading the change history…</p>}
      {history?.length === 0 && <p>No changes yet.</p>}
      {history && history.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Who</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {history.map(/*
     * Transform the current collection item into its displayed or normalized value.
     */
    (entry, index) => (
              <tr key={`${entry.created_at}-${index}`}>
                <td>{formatChangeTime(entry.created_at)}</td>
                <td>{entry.corrected_by_name ?? "Unknown staff member"}</td>
                <td style={{ overflowWrap: "anywhere" }}>
                  {entry.learner_name ?? "Unknown learner"}: {statusLabel(entry.old_status)} →{" "}
                  {statusLabel(entry.new_status)}
                  {entry.reason && ` (${entry.reason})`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/*
 * Render the add and mark form interface and its associated content.
 */
function AddAndMarkForm({
  sessionId,
  onAdded,
  onPastSession,
  onLoginRequired,
}: {
  sessionId: string;
  onAdded: (learner: ListedLearner, record: AttendanceRecord | null, count: number) => void;
  onPastSession: () => void;
  onLoginRequired: () => void;
}) {
  const [name, setName] = useState({ first_name: "", family_name: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<Message | null>(null);
  const [saving, setSaving] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  /*
   * Update the edited form field and clear its obsolete feedback.
   */
  function change(field: string, value: string) {
    setName(/*
     * Compute the next name state from its previous value.
     */
    (current) => ({ ...current, [field]: value }));
    setErrors(/*
     * Compute the next errors state from its previous value.
     */
    (current) => ({ ...current, [field]: undefined }));
  }

  /*
   * Validate and submit the attendance screen form, updating its success and error
   * state.
   */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    const found = checkNames({ ...name, first_language: "", contact: "" });
    setErrors(found);
    setMessage(null);
    if (found.first_name || found.family_name) {
      document.getElementById(found.first_name ? "learner-first-name" : "learner-family-name")?.focus();
      return;
    }

    setSaving(true);
    try {
      const result = await addAndMarkPresent(sessionId, name);
      onAdded(result.learner, result.attendance, result.present_count);
      const who = fullName(result.learner);
      setMessage({
        kind: "success",
        text: result.learner_added
          ? `${who} is added to the class list and marked present`
          : `${who} is already on the class list and is now marked present`,
      });
      setName({ first_name: "", family_name: "" });
      firstFieldRef.current?.focus();
    } catch (error) {
      if (error instanceof AlreadySignedInError) setMessage({ kind: "info", text: error.message });
      else if (error instanceof LearnerFieldError) setErrors({ [error.field]: error.message });
      else if (error instanceof PastSessionError) onPastSession();
      else if (error instanceof LoginRequiredError) onLoginRequired();
      else setMessage({ kind: "error", text: CHANGE_FAILED });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="add-and-mark-title" className="no-print">
      <h2 id="add-and-mark-title">Learner not on the list</h2>
      <form onSubmit={/*
     * Handle the submit event for this control.
     */
    (event) => void submit(event)} noValidate aria-busy={saving}>
        <div className="grid-2">
          <TextField
            ref={firstFieldRef}
            name="first_name"
            label="First name"
            required
            value={name.first_name}
            error={errors.first_name}
            onChange={change}
          />
          <TextField
            name="family_name"
            label="Family name"
            required
            value={name.family_name}
            error={errors.family_name}
            onChange={change}
          />
        </div>
        <button type="submit" className="btn">
          {saving ? "Saving…" : "Add and mark present"}
        </button>
        <MessageBox message={message} />
      </form>
    </section>
  );
}
