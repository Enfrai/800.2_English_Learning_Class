"use client";

import MaterialsScreen from "@/components/materials/materials-screen";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { type FieldErrors, TextField, checkNames } from "@/components/learners/learner-form";
import {
  ALREADY_SIGNED_IN,
  CHECKIN_CLOSED,
  NAME_NOT_FOUND,
  SIGNED_IN,
  UNAVAILABLE,
  getCheckin,
  signIn,
} from "@/lib/checkin-api";
import { formatSessionDate } from "@/lib/dates";

type PageState = "loading" | "open" | "signed-in" | "closed" | "failed";
type Message = { kind: "info" | "error"; text: string };

export default function SignInScreen({ token }: { token: string }) {
  const [state, setState] = useState<PageState>("loading");
  const [sessionDate, setSessionDate] = useState("");
  const [name, setName] = useState({ first_name: "", family_name: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState<Message | null>(null);
  const [sending, setSending] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    void getCheckin(token).then((checkin) => {
      if (!active) return;
      if (checkin.kind === "open") {
        setSessionDate(checkin.sessionDate);
        setState("open");
      } else setState(checkin.kind);
    });
    return () => {
      active = false;
    };
  }, [token]);

  function change(field: string, value: string) {
    setName((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setMessage(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending) return;
    // Checked here so an empty name never counts as a wrong try.
    const found = checkNames({ ...name, first_language: "", contact: "" });
    setErrors(found);
    setMessage(null);
    if (found.first_name || found.family_name) {
      document.getElementById(found.first_name ? "learner-first-name" : "learner-family-name")?.focus();
      return;
    }

    setSending(true);
    const result = await signIn(token, name.first_name, name.family_name);
    setSending(false);
    if (result.kind === "signed-in") setState("signed-in");
    else if (result.kind === "closed") setState("closed");
    else if (result.kind === "already") setMessage({ kind: "info", text: ALREADY_SIGNED_IN });
    else if (result.kind === "not-found") {
      setMessage({ kind: "error", text: NAME_NOT_FOUND });
      firstFieldRef.current?.focus();
    } else if (result.kind === "too-many") setMessage({ kind: "error", text: result.message });
    else setMessage({ kind: "error", text: UNAVAILABLE });
  }

  return (
    <>
      <h1>Sign in to class</h1>
      {state === "loading" && <p role="status">Loading…</p>}
      {sessionDate && state !== "closed" && <p className="sub">{formatSessionDate(sessionDate)}</p>}

      {state === "closed" && (
        <div className="msg msg-warning" role="alert">
          {CHECKIN_CLOSED}
        </div>
      )}
      {state === "failed" && (
        <div className="msg msg-error" role="alert">
          {UNAVAILABLE}
        </div>
      )}
      {state === "signed-in" && (
        <>
          <div className="msg msg-success" role="status">
            {SIGNED_IN}
          </div>
          <MaterialsScreen embedded />
          <a className="btn btn-big" href="/materials">Lesson materials</a>
        </>
      )}

      {state === "open" && (
        <form onSubmit={(event) => void submit(event)} noValidate aria-busy={sending}>
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
          <button type="submit" className="btn btn-big" style={{ width: "100%" }}>
            {sending ? "Signing in…" : "Sign in"}
          </button>
          {message && (
            <div
              className={`msg msg-${message.kind}`}
              role={message.kind === "error" ? "alert" : "status"}
            >
              {message.text}
            </div>
          )}
        </form>
      )}
    </>
  );
}
