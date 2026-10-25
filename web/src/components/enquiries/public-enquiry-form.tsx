"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import styles from "./public-enquiry-form.module.css";

const EMAIL_ERROR = "Please enter a valid email address";
const MESSAGE_ERROR = "Message must be 500 characters or fewer";
const CONSENT_ERROR = "Please consent to being contacted by the club";
const SUCCESS = "Thank you, the club will contact you";
const EMPTY = { name: "", contact_type: "email" as "email" | "phone", contact: "", message: "", consent: false };
type Field = "name" | "contact" | "message" | "consent";
type Errors = Partial<Record<Field, string>>;

/** Public, standalone form. The backend remains the validation authority. */
export default function PublicEnquiryForm() {
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const pending = useRef(false);
  const focusAfterEnable = useRef<Field | null>(null);
  const [values, setValues] = useState({ ...EMPTY });
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    // React must commit disabled=false before a server-rejected field can receive focus.
    if (!busy && focusAfterEnable.current) {
      formRef.current?.querySelector<HTMLElement>(`[name="${focusAfterEnable.current}"]`)?.focus();
      focusAfterEnable.current = null;
    }
  }, [busy, errors]);

  function showErrors(found: Errors) {
    setErrors(found);
    const first = Object.keys(found)[0];
    if (first) formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Close the same-tick double-submit gap before disabled controls render.
    if (pending.current) return;
    setNotice(""); setSuccess(false);
    const found: Errors = {};
    if (!values.name.trim() || Array.from(values.name.trim()).length > 150) found.name = "Name must contain 1 to 150 characters";
    const contact = values.contact.trim();
    if (values.contact_type === "email") {
      const parts = contact.split("@");
      const [local = "", domain = ""] = parts;
      if (parts.length !== 2 || contact.length > 255 || !/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}$/.test(local)
        || local.startsWith(".") || local.endsWith(".") || local.includes("..") || !domain.includes(".")
        || !domain.split(".").every(label => /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))) found.contact = EMAIL_ERROR;
    } else {
      const digits = contact.replace(/[^0-9]/g, "");
      if (contact.length > 255 || !/^\+?[0-9 ()-]+$/.test(contact) || digits.length < 7 || digits.length > 15) found.contact = "Please enter a valid phone number";
    }
    // Count code points like Python. Do not silently truncate pasted text.
    if (Array.from(values.message).length > 500) found.message = MESSAGE_ERROR;
    if (!values.consent) found.consent = CONSENT_ERROR;
    showErrors(found);
    if (Object.keys(found).length) return;
    pending.current = true; setBusy(true);
    try {
      const response = await fetch("/api/user/enquiries", {
        method: "POST", credentials: "omit", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...values, name: values.name.trim(), contact }),
      });
      const data: unknown = await response.json().catch(() => null);
      const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
      // Only render agreed validation messages, never arbitrary API internals.
      const field = detail === EMAIL_ERROR || detail === "Please enter a valid phone number" ? "contact"
        : detail === MESSAGE_ERROR ? "message" : detail === CONSENT_ERROR ? "consent"
        : detail === "Name must contain 1 to 150 characters" ? "name" : null;
      if (response.status === 422 && field && typeof detail === "string") {
        focusAfterEnable.current = field;
        setErrors({ [field]: detail });
      } else if (response.status === 201) {
        setValues({ ...EMPTY }); setErrors({}); setSuccess(true); setNotice(SUCCESS);
      } else {
        setNotice(response.status === 429 ? "Too many requests. Please try again later." : "Unable to send your enquiry. Please try again later.");
      }
    } catch {
      // A lost response may follow a committed write. Never retry automatically.
      setNotice("We could not confirm your submission. Please try again later.");
    } finally {
      pending.current = false; setBusy(false);
    }
  }

  function error(field: Field) {
    return errors[field] && <p id={`${id}-${field}-error`} className={styles.error} role="alert">{errors[field]}</p>;
  }
  function accessibility(field: Field) {
    return { "aria-invalid": Boolean(errors[field]), "aria-describedby": errors[field] ? `${id}-${field}-error` : undefined };
  }

  return <section className={styles.form} aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`}>Register interest in classes</h2>
    <form ref={formRef} onSubmit={submit} noValidate aria-busy={busy}>
      <fieldset disabled={busy}>
        <legend>Your enquiry</legend>
        <label htmlFor={`${id}-name`}>Name (required)</label>
        <input id={`${id}-name`} name="name" autoComplete="name" required value={values.name} {...accessibility("name")} onChange={e => setValues({ ...values, name: e.target.value })} />
        {error("name")}
        <label htmlFor={`${id}-type`}>Email/Phone</label>
        <select id={`${id}-type`} value={values.contact_type} onChange={e => { setValues({ ...values, contact_type: e.target.value as "email" | "phone" }); setErrors({ ...errors, contact: undefined }); }}>
          <option value="email">Email</option><option value="phone">Phone</option>
        </select>
        <label htmlFor={`${id}-contact`}>Contact (required)</label>
        <input id={`${id}-contact`} name="contact" type={values.contact_type === "email" ? "email" : "tel"} autoComplete={values.contact_type === "email" ? "email" : "tel"} required value={values.contact} {...accessibility("contact")} onChange={e => setValues({ ...values, contact: e.target.value })} />
        {error("contact")}
        <label htmlFor={`${id}-message`}>Message (optional, maximum 500 characters)</label>
        <textarea id={`${id}-message`} name="message" rows={4} value={values.message} {...accessibility("message")} onChange={e => {
          const message = e.target.value;
          setValues({ ...values, message });
          setErrors({ ...errors, message: Array.from(message).length > 500 ? MESSAGE_ERROR : undefined });
        }} />
        {error("message")}
        <label className={styles.consent} htmlFor={`${id}-consent`}>
          <input id={`${id}-consent`} name="consent" type="checkbox" required checked={values.consent} {...accessibility("consent")} onChange={e => setValues({ ...values, consent: e.target.checked })} />
          I agree that the club may contact me about classes. (Required)
        </label>
        {error("consent")}
        <button type="submit" disabled={busy}>{busy ? "Sending…" : "Send enquiry"}</button>
      </fieldset>
      {busy && <p role="status">Sending your enquiry…</p>}
      {notice && <p className={success ? styles.success : styles.error} role={success ? "status" : "alert"}>{notice}</p>}
    </form>
  </section>;
}
