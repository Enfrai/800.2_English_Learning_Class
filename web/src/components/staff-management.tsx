/* Manage staff accounts with the shared Ako controls and feedback styles.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Button, TextField } from "./ako-controls";
import styles from "./staff-management.module.css";

// Keep the browser model limited to public fields; credentials never belong here.
type StaffAccount = {
  id: string;
  username: string;
  display_name: string;
  role: "teacher" | "coordinator";
  is_active: boolean;
};
type Notice = { kind: "success" | "error"; message: string };
// US-002 AC5; same text as the User service (Test Plan UT-12).
const LAST_COORDINATOR = "At least one coordinator must stay active";
class AccessLost extends Error {}

function isAccount(value: unknown): value is StaffAccount {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return typeof row.id === "string" && typeof row.username === "string"
    && typeof row.display_name === "string" && typeof row.is_active === "boolean"
    && (row.role === "teacher" || row.role === "coordinator");
}

/** Teacher management, plus Coordinator deactivation for AC5. SessionShell and the server remain the permission boundary. */
export default function StaffManagement() {
  const router = useRouter();
  const [teachers, setTeachers] = useState<StaffAccount[]>([]);
  // Shown only so a Coordinator can be deactivated (AC5); never renamed here.
  const [coordinators, setCoordinators] = useState<StaffAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loadError, setLoadError] = useState("");
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [editing, setEditing] = useState<StaffAccount | null>(null);
  const [editName, setEditName] = useState("");
  const [confirming, setConfirming] = useState<StaffAccount | null>(null);
  const pending = useRef(false);
  const mounted = useRef(false);
  const accessLost = useRef(false);
  const disabled = loading || busy || !loaded || blocked;

  /** Never supply Origin or tokens manually: same-origin cookies use the existing CSRF checks. */
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(`/api/user${path}`, {
      ...init, credentials: "same-origin", cache: "no-store",
    });
    if (response.status === 401 || response.status === 403) {
      if (mounted.current) {
        accessLost.current = true;
        setBlocked(true);
        setTeachers([]);
        setCoordinators([]);
        setPassword("");
        setEditing(null);
        setConfirming(null);
        if (response.status === 401) router.replace("/");
        else setNotice({ kind: "error", message: "You do not have permission" });
      }
      throw new AccessLost();
    }
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
      // Render only agreed API messages, never arbitrary server errors or validation input.
      if (response.status === 409 && detail === "Username already taken") throw new Error(detail);
      if (response.status === 409 && detail === LAST_COORDINATOR) throw new Error(detail);
      if (response.status === 422 && detail === "Password must be at least 8 characters") throw new Error(detail);
      if (response.status === 422) throw new Error("Please check the form fields and try again.");
      if (response.status === 404) throw new Error("This account is no longer available. Refresh the list.");
      throw new Error("Unable to complete the request. Please try again.");
    }
    return response;
  }, [router]);

  /** Loading is passive: it reads staff without refreshing the authentication session. */
  const loadTeachers = useCallback(async (signal?: AbortSignal) => {
    const response = await request("/staff", { signal });
    const data: unknown = await response.json();
    if (!Array.isArray(data) || !data.every(isAccount)) throw new Error("Unable to read the staff list. Please try again.");
    if (mounted.current && !accessLost.current && !signal?.aborted) {
      // Teachers get every action; Coordinators can only be deactivated (AC5).
      setTeachers(data.filter(account => account.role === "teacher"));
      setCoordinators(data.filter(account => account.role === "coordinator"));
      setLoaded(true);
      setLoadError("");
    }
  }, [request]);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void loadTeachers(controller.signal).catch(reason => {
      if (!controller.signal.aborted && mounted.current && !(reason instanceof AccessLost)) {
        setLoadError("Unable to load Teacher accounts. Please try again.");
      }
    }).finally(() => {
      if (!controller.signal.aborted && mounted.current) setLoading(false);
    });
    return () => { mounted.current = false; controller.abort(); };
  }, [loadTeachers]);

  async function refreshList() {
    if (pending.current || loading || accessLost.current) return;
    setLoading(true);
    try { await loadTeachers(); }
    catch (reason) {
      if (mounted.current && !(reason instanceof AccessLost)) setLoadError("Unable to load Teacher accounts. Please try again.");
    } finally { if (mounted.current) setLoading(false); }
  }

  /** A ref closes the same-tick double-submit gap before React renders disabled buttons. */
  async function mutate(path: string, method: "POST" | "PATCH", body: object | undefined, message: string): Promise<boolean> {
    if (pending.current || disabled || accessLost.current) return false;
    pending.current = true;
    setBusy(true);
    setNotice(null);
    try {
      const response = await request(path, {
        method,
        ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
      });
      const account: unknown = await response.json();
      if (!isAccount(account)) throw new Error("Unexpected response. Refresh the list before trying again.");
      if (!mounted.current || accessLost.current) return false;
      // Show the committed change immediately; a failed follow-up GET must not imply the write failed.
      const setList = account.role === "teacher" ? setTeachers : setCoordinators;
      setList(current => [...current.filter(row => row.id !== account.id), account]
        .sort((a, b) => a.username.localeCompare(b.username)));
      setNotice({ kind: "success", message });
      setEditing(null);
      setConfirming(null);
      try { await loadTeachers(); }
      catch (reason) {
        if (mounted.current && !(reason instanceof AccessLost)) setLoadError("Changes saved, but the list could not be refreshed. Please refresh the list.");
      }
      return !accessLost.current;
    } catch (reason) {
      if (mounted.current && !(reason instanceof AccessLost)) {
        setNotice({ kind: "error", message: reason instanceof Error && !(reason instanceof TypeError)
          ? reason.message : "Unable to save changes. Refresh the list before trying again." });
      }
      return false;
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  async function createTeacher(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || disabled) return;
    if (!name.trim() || !username.trim()) {
      setNotice({ kind: "error", message: "Name and username are required" });
      return;
    }
    // Count Unicode code points like Python; the backend independently enforces this rule.
    if (Array.from(password).length < 8) {
      setNotice({ kind: "error", message: "Password must be at least 8 characters" });
      return;
    }
    try {
      const saved = await mutate("/staff", "POST", { display_name: name, username, temporary_password: password }, "Teacher account created.");
      if (saved && mounted.current) { setName(""); setUsername(""); }
    } finally {
      // Passwords live only in this form's memory and are discarded after an API submission attempt.
      if (mounted.current) setPassword("");
    }
  }

  async function renameTeacher(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing || pending.current || disabled) return;
    if (!editName.trim()) { setNotice({ kind: "error", message: "Name is required" }); return; }
    // Send an explicit field allowlist rather than serializing the account object.
    await mutate(`/staff/${encodeURIComponent(editing.id)}`, "PATCH", { display_name: editName }, "Teacher name updated.");
  }

  async function deactivateTeacher() {
    if (!confirming || !confirming.is_active) return;
    // This action is reached only from the separate confirmation step; it never deletes history.
    const message = confirming.role === "teacher" ? "Teacher account deactivated." : "Coordinator account deactivated.";
    await mutate(`/staff/${encodeURIComponent(confirming.id)}/deactivate`, "POST", undefined, message);
  }

  return <section className={styles.staff} aria-labelledby="staff-heading">
    <h1 id="staff-heading">Account management</h1>
    <p className="sub">Create and manage Teacher accounts.</p>
    {notice && <p className={`msg msg-${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>{notice.message}</p>}
    {!blocked && <>
      {loadError && <p className="msg msg-error" role="alert">{loadError}</p>}
      <section aria-labelledby="create-heading" className={styles.section}>
        <h2 id="create-heading">Add Teacher</h2>
        <form onSubmit={createTeacher} noValidate aria-label="Add Teacher" aria-busy={busy}>
          <TextField label="Name" name="display_name" maxLength={150} required disabled={disabled} value={name} onInput={e => setName((e.target as HTMLInputElement).value)} />
          <TextField label="Username" name="username" maxLength={100} autocomplete="off" required disabled={disabled} value={username} onInput={e => setUsername((e.target as HTMLInputElement).value)} />
          <TextField label="Temporary Password" name="temporary_password" type="password" autocomplete="new-password" required disabled={disabled} value={password} onInput={e => setPassword((e.target as HTMLInputElement).value)} />
          <Button type="submit" disabled={disabled}>{busy ? "Saving…" : "Create Teacher"}</Button>
        </form>
      </section>
      {editing && <section className={styles.section} aria-labelledby="edit-heading">
        <h2 id="edit-heading">Edit Teacher name</h2>
        <p>Username: {editing.username}</p>
        <form onSubmit={renameTeacher} noValidate aria-label="Edit Teacher name" aria-busy={busy}>
          <TextField label="Name" name="edit_display_name" maxLength={150} required disabled={disabled} value={editName} onInput={e => setEditName((e.target as HTMLInputElement).value)} />
          <div className={styles.actions}>
            <Button type="submit" disabled={disabled}>Save name</Button>
            <Button className="btn-secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel edit</Button>
          </div>
        </form>
      </section>}
      {confirming && <section className={`card ${styles.confirmation}`} aria-labelledby="confirm-heading">
        <h2 id="confirm-heading">{confirming.role === "teacher" ? "Deactivate Teacher?" : "Deactivate Coordinator?"}</h2>
        <p>Deactivate {confirming.display_name} ({confirming.username})? They will no longer be able to sign in. Their lessons and attendance history will be kept.
          {confirming.role === "coordinator" && " At least one coordinator must stay active."}</p>
        <div className={styles.actions}>
          <Button className="btn-danger" type="button" disabled={disabled} onClick={() => void deactivateTeacher()}>Confirm deactivation</Button>
          <Button className="btn-secondary" type="button" disabled={busy} onClick={() => setConfirming(null)}>Cancel deactivation</Button>
        </div>
      </section>}
      <section className={styles.section} aria-labelledby="list-heading" aria-busy={loading}>
        <div className={styles.listHeader}>
          <h2 id="list-heading">Teacher accounts</h2>
          <Button className="btn-secondary" type="button" disabled={busy || loading} onClick={() => void refreshList()}>Refresh list</Button>
        </div>
        {loading && <p role="status">Loading Teacher accounts…</p>}
        {!loading && loaded && teachers.length === 0 && <p role="status">No Teacher accounts yet.</p>}
        <ul className={styles.list} aria-label="Teacher accounts">
          {teachers.map(teacher => <li key={teacher.id} className={`card ${styles.card}`}>
            <div className={styles.details}><h3>{teacher.display_name}</h3><p>Username: {teacher.username}</p><p>Status: <span className={`badge ${teacher.is_active ? "badge-reviewed" : "badge-inactive"}`}>{teacher.is_active ? "Active" : "Inactive"}</span></p></div>
            <div className={styles.actions}>
              <Button className="btn-secondary" type="button" disabled={disabled} aria-label={`Edit ${teacher.username}`} onClick={() => { setEditing(teacher); setEditName(teacher.display_name); setConfirming(null); setNotice(null); }}>Edit name</Button>
              {teacher.is_active && <Button className="btn-secondary" type="button" disabled={disabled} aria-label={`Deactivate ${teacher.username}`} onClick={() => { setConfirming(teacher); setEditing(null); setNotice(null); }}>Deactivate</Button>}
            </div>
          </li>)}
        </ul>
      </section>
      <section className={styles.section} aria-labelledby="coordinator-list-heading">
        <h2 id="coordinator-list-heading">Coordinator accounts</h2>
        <ul className={styles.list} aria-label="Coordinator accounts">
          {coordinators.map(account => <li key={account.id} className={`card ${styles.card}`}>
            <div className={styles.details}><h3>{account.display_name}</h3><p>Username: {account.username}</p><p>Status: <span className={`badge ${account.is_active ? "badge-reviewed" : "badge-inactive"}`}>{account.is_active ? "Active" : "Inactive"}</span></p></div>
            <div className={styles.actions}>
              {account.is_active && <Button className="btn-secondary" type="button" disabled={disabled} aria-label={`Deactivate ${account.username}`} onClick={() => { setConfirming(account); setEditing(null); setNotice(null); }}>Deactivate</Button>}
            </div>
          </li>)}
        </ul>
      </section>
    </>}
  </section>;
}
