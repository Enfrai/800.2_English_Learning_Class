/* "Record a review" form for coordinators on the lesson page (UI design 6.10, US-008 AC2, AC3).
 * Author: Pei Wu
 * Date: 26 Oct 2026
 */

"use client";

import { useRef, useState, type FormEvent } from "react";
import { LessonError, LoginRequiredError, messageFor, recordReview } from "@/lib/lessons-api";
import styles from "./lessons.module.css";

// Messages from the Lesson service (maori_review.py); the service checks again.
const NAME_REQUIRED = "Reviewer name is required";
const DATE_REQUIRED = "Review date is required";
const DATE_IN_FUTURE = "Review date cannot be in the future";
const MAX_NAME_LENGTH = 150;

/** The club's date as YYYY-MM-DD, so "the future" means the same as on the server. */
function clubToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Pacific/Auckland" }).format(new Date());
}

export default function ReviewForm({ lessonId, onSaved, onLoginRequired }: {
  lessonId: string;
  onSaved: () => Promise<void>;
  onLoginRequired: () => void;
}) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  function showErrors(found: Record<string, string>) {
    setErrors(found);
    const first = Object.keys(found)[0];
    if (first) form.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const found: Record<string, string> = {};
    if (!name.trim()) found.reviewer_name = NAME_REQUIRED;
    if (!date) found.review_date = DATE_REQUIRED;
    else if (date > clubToday()) found.review_date = DATE_IN_FUTURE;
    setMessage("");
    showErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await recordReview(lessonId, { reviewer_name: name, review_date: date });
      setName(""); setDate("");
      await onSaved();
    } catch (error) {
      if (error instanceof LoginRequiredError) onLoginRequired();
      else if (error instanceof LessonError && Object.keys(error.fields).length) showErrors(error.fields);
      else setMessage(messageFor(error));
    } finally { setBusy(false); }
  }

  const fieldError = (field: string) => errors[field] &&
    <p id={`${field}-error`} className="msg msg-error" role="alert">{errors[field]}</p>;
  const attrs = (field: string) => ({
    "aria-invalid": Boolean(errors[field]),
    "aria-describedby": [field === "review_date" ? "review-date-hint" : "", errors[field] ? `${field}-error` : ""].filter(Boolean).join(" ") || undefined,
  });
  return <section className={`card no-print ${styles.confirmation}`} aria-labelledby="review-heading">
    <h2 id="review-heading">Record a review</h2>
    <p className="sub">Coordinators only. Record the review after the Kaiārahi confirms it outside Ako.</p>
    <form ref={form} onSubmit={save} noValidate aria-busy={busy}>
      <div className="field"><label htmlFor="reviewer-name" className="req">Reviewer name</label>
        <input id="reviewer-name" name="reviewer_name" type="text" maxLength={MAX_NAME_LENGTH} value={name} disabled={busy}
          {...attrs("reviewer_name")} onChange={e => setName(e.target.value)} />
        {fieldError("reviewer_name")}</div>
      <div className="field"><label htmlFor="review-date" className="req">Review date</label>
        <input id="review-date" name="review_date" type="date" max={clubToday()} value={date} disabled={busy}
          {...attrs("review_date")} onChange={e => setDate(e.target.value)} />
        <p id="review-date-hint" className="hint">Not in the future</p>
        {fieldError("review_date")}</div>
      <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : "Save review"}</button>
      {message && <p className="msg msg-error" role="alert">{message}</p>}
    </form>
  </section>;
}
