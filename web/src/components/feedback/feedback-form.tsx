/* Collect accessible public feedback and retain entered text after submission errors.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

"use client";

import { useRef, useState, type FormEvent } from "react";
import { submitFeedback, validateFeedback, type FeedbackInput } from "@/lib/feedback-api";
import styles from "./feedback.module.css";

const empty: FeedbackInput = { title: "", email: "", description: "" };

export default function FeedbackForm() {
  const [input, setInput] = useState<FeedbackInput>(empty);
  const [errors, setErrors] = useState<Partial<Record<keyof FeedbackInput, string>>>({});
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [success, setSuccess] = useState(false);
  const pending = useRef(false), form = useRef<HTMLFormElement>(null);
  function change(field: keyof FeedbackInput, value: string) {
    setInput(current => ({ ...current, [field]: value }));
    setErrors(current => ({ ...current, [field]: undefined }));
    setMessage(""); setSuccess(false);
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    setMessage(""); setSuccess(false);
    const found = validateFeedback(input);
    setErrors(found);
    if (Object.keys(found).length) {
      form.current?.querySelector<HTMLElement>(`[name="${Object.keys(found)[0]}"]`)?.focus();
      return;
    }
    pending.current = true; setBusy(true);
    try {
      const result = await submitFeedback(input);
      setInput(empty); setSuccess(true); setMessage(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to confirm delivery. Please try again later.");
    } finally { pending.current = false; setBusy(false); }
  }
  const attrs = (field: keyof FeedbackInput) => ({
    "aria-invalid": Boolean(errors[field]),
    "aria-describedby": errors[field] ? `feedback-${field}-error` : undefined,
  });
  const error = (field: keyof FeedbackInput) => errors[field] && <p className="msg msg-error" id={`feedback-${field}-error`} role="alert">{errors[field]}</p>;
  return <form className={styles.form} ref={form} onSubmit={send} noValidate aria-busy={busy}>
    <div className="field"><label htmlFor="feedback-title" className="req">Title</label>
      <input id="feedback-title" name="title" required maxLength={200} value={input.title} disabled={busy} {...attrs("title")} onChange={event => change("title", event.target.value)} />
      {error("title")}</div>
    <div className="field"><label htmlFor="feedback-email" className="req">Email</label>
      <input id="feedback-email" name="email" type="email" autoComplete="email" required maxLength={254} value={input.email} disabled={busy} {...attrs("email")} onChange={event => change("email", event.target.value)} />
      {error("email")}</div>
    <div className="field"><label htmlFor="feedback-description" className="req">Description</label>
      <textarea id="feedback-description" name="description" required maxLength={5000} value={input.description} disabled={busy} {...attrs("description")} onChange={event => change("description", event.target.value)} />
      <p className="hint">Up to 5,000 characters. Do not include passwords or private learner information.</p>{error("description")}</div>
    <button className="btn" type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit feedback"}</button>
    {message && <p className={`msg ${success ? "msg-success" : "msg-error"}`} role={success ? "status" : "alert"}>{message}</p>}
  </form>;
}
