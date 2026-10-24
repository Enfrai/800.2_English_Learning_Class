/* Attendance (sign-in) page for one class session (UI design document 6.6, US-004).
 * Author: Pei Wu
 * Date: 23 Oct 2026
 */

"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { type FieldErrors, TextField, checkNames } from "@/components/learners/learner-form";
import { LoginRequiredError } from "@/lib/api";
import {
  AlreadySignedInError,
  type AttendanceRecord,
  NotFoundError,
  PastSessionError,
  addAndMarkPresent,
  getAttendance,
  markPresent,
  unmarkPresent,
} from "@/lib/attendance-api";
import { type Learner, LearnerFieldError, listLearners } from "@/lib/learners-api";

type LoadState = "loading" | "ready" | "login-required" | "not-found" | "failed";
type Message = { kind: "info" | "warning" | "error" | "success"; text: string };
type ListedLearner = Pick<Learner, "id" | "first_name" | "family_name" | "first_language">;

// Message catalogue, UI design document section 7.
const PAST_ATTENDANCE_LOCKED = "Only a coordinator can correct past attendance";
const CHANGE_FAILED = "The change could not be saved. Please try again.";

function fullName(learner: Pick<Learner, "first_name" | "family_name">): string {
  return `${learner.first_name} ${learner.family_name}`;
}

function byFamilyThenFirstName(a: ListedLearner, b: ListedLearner): number {
  return (
    a.family_name.localeCompare(b.family_name, undefined, { sensitivity: "base" }) ||
    a.first_name.localeCompare(b.first_name, undefined, { sensitivity: "base" })
  );
}

function formatTime(isoTime: string): string {
  return new Date(isoTime).toLocaleTimeString("en-NZ", { hour: "numeric", minute: "2-digit" });
}

function formatSessionDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-NZ", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function MessageBox({ message }: { message: Message | null }) {
  if (!message) return null;
  const urgent = message.kind === "error" || message.kind === "warning";
  return (
    <div className={`msg msg-${message.kind}`} role={urgent ? "alert" : "status"}>
      {message.text}
    </div>
  );
}

export default function AttendanceScreen({ sessionId }: { sessionId: string }) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [learners, setLearners] = useState<ListedLearner[]>([]);
  const [records, setRecords] = useState<Map<string, AttendanceRecord>>(new Map());
  const [presentCount, setPresentCount] = useState(0);
  const [sessionDate, setSessionDate] = useState("");
  const [editable, setEditable] = useState(false);
  // Learners whose tick is being saved, with the state the teacher chose.
  const [pending, setPending] = useState<Map<string, boolean>>(new Map());
  // Messages about one learner are shown in that learner's row (UI kit rule 3).
  const [rowMessages, setRowMessages] = useState<Map<string, Message>>(new Map());

  const load = useCallback(async () => {
    try {
      const [classList, attendance] = await Promise.all([
        listLearners(),
        getAttendance(sessionId),
      ]);
      setLearners(classList);
      setRecords(new Map(attendance.records.map((record) => [record.learner_id, record])));
      setPresentCount(attendance.present_count);
      setSessionDate(attendance.session_date);
      setEditable(attendance.editable);
      setLoadState("ready");
    } catch (error) {
      if (error instanceof LoginRequiredError) setLoadState("login-required");
      else if (error instanceof NotFoundError) setLoadState("not-found");
      else setLoadState("failed");
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  function setRecord(learnerId: string, record: AttendanceRecord | null) {
    setRecords((current) => {
      const next = new Map(current);
      if (record) next.set(learnerId, record);
      else next.delete(learnerId);
      return next;
    });
  }

  function setRowMessage(learnerId: string, message: Message | null) {
    setRowMessages((current) => {
      const next = new Map(current);
      if (message) next.set(learnerId, message);
      else next.delete(learnerId);
      return next;
    });
  }

  function lockPastSession() {
    setEditable(false);
  }

  async function toggle(learner: ListedLearner, present: boolean) {
    if (pending.has(learner.id)) return;
    setPending((current) => new Map(current).set(learner.id, present));
    setRowMessage(learner.id, null);
    try {
      const change = present
        ? await markPresent(sessionId, learner.id)
        : await unmarkPresent(sessionId, learner.id);
      setRecord(learner.id, change.attendance);
      setPresentCount(change.present_count);
    } catch (error) {
      if (error instanceof AlreadySignedInError) {
        setRowMessage(learner.id, { kind: "info", text: error.message });
        await load();
      } else if (error instanceof PastSessionError) lockPastSession();
      else if (error instanceof NotFoundError) await load();
      else if (error instanceof LoginRequiredError) setLoadState("login-required");
      else setRowMessage(learner.id, { kind: "error", text: CHANGE_FAILED });
    } finally {
      setPending((current) => {
        const next = new Map(current);
        next.delete(learner.id);
        return next;
      });
    }
  }

  function handleAdded(learner: ListedLearner, record: AttendanceRecord | null, count: number) {
    setLearners((current) =>
      current.some((listed) => listed.id === learner.id)
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
        <div className="msg msg-error" role="alert">
          Class session not found
        </div>
      </>
    );
  }

  return (
    <>
      <h1>Attendance</h1>
      {loadState === "loading" && <p role="status">Loading the class list…</p>}
      {loadState === "failed" && (
        <div className="msg msg-error" role="alert">
          The class list could not be loaded. Please try again.{" "}
          <button type="button" className="btn btn-secondary" onClick={() => void load()}>
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
            <button type="button" className="btn btn-secondary no-print" onClick={() => window.print()}>
              Print this list
            </button>
            {/* QR check-in is US-011 (Later). */}
            <button type="button" className="btn btn-later no-print" disabled>
              Open check-in with QR code (later)
            </button>
          </div>
          {!editable && (
            <div className="msg msg-warning" role="alert">
              {PAST_ATTENDANCE_LOCKED}
            </div>
          )}
          <ClassList
            learners={learners}
            records={records}
            pending={pending}
            rowMessages={rowMessages}
            editable={editable}
            onToggle={(learner, present) => void toggle(learner, present)}
          />
          {editable && (
            <AddAndMarkForm
              sessionId={sessionId}
              onAdded={handleAdded}
              onPastSession={lockPastSession}
              onLoginRequired={() => setLoadState("login-required")}
            />
          )}
        </>
      )}
    </>
  );
}

function ClassList({
  learners,
  records,
  pending,
  rowMessages,
  editable,
  onToggle,
}: {
  learners: ListedLearner[];
  records: Map<string, AttendanceRecord>;
  pending: Map<string, boolean>;
  rowMessages: Map<string, Message>;
  editable: boolean;
  onToggle: (learner: ListedLearner, present: boolean) => void;
}) {
  if (learners.length === 0) {
    return <div className="msg msg-info">No learners yet. Add a learner below to mark them present.</div>;
  }
  return (
    <table className="data" style={{ marginTop: "var(--space-4)" }}>
      <thead>
        <tr>
          <th scope="col">Present</th>
          <th scope="col">Name</th>
          <th scope="col">First language</th>
          <th scope="col">Time</th>
        </tr>
      </thead>
      <tbody>
        {learners.map((learner) => {
          const record = records.get(learner.id);
          const checkboxId = `present-${learner.id}`;
          return (
            <tr key={learner.id}>
              <td>
                <div className="check">
                  <input
                    id={checkboxId}
                    type="checkbox"
                    // Show the teacher's choice at once; it reverts if saving fails.
                    checked={pending.get(learner.id) ?? Boolean(record)}
                    aria-busy={pending.has(learner.id)}
                    disabled={!editable}
                    onChange={(event) => onToggle(learner, event.target.checked)}
                  />
                </div>
              </td>
              <td>
                {/* Clicking the name ticks the box; it also names the box for screen readers. */}
                <label htmlFor={checkboxId}>{fullName(learner)}</label>
              </td>
              <td>{learner.first_language ?? "–"}</td>
              <td>
                {record && (
                  <>
                    <span className="badge badge-present">Present</span> {formatTime(record.recorded_at)}
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

  function change(field: string, value: string) {
    setName((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

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
      <form onSubmit={(event) => void submit(event)} noValidate aria-busy={saving}>
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
