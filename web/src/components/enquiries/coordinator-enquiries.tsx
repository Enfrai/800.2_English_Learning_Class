"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../session-context";
import styles from "./coordinator-enquiries.module.css";

type Enquiry = { id: string; name: string; contact: string; message: string | null; created_at: string };
type State = "loading" | "ready" | "login" | "forbidden" | "error";
const PAGE_SIZE = 20;
const MAX_OFFSET = 10000;

function isEnquiry(value: unknown): value is Enquiry {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return typeof row.id === "string" && typeof row.name === "string"
    && typeof row.contact === "string" && (row.message === null || typeof row.message === "string")
    && typeof row.created_at === "string" && Number.isFinite(Date.parse(row.created_at));
}

/** SessionShell supplies UI identity; the API independently authorizes the cookie. */
export default function CoordinatorEnquiries() {
  const session = useSession();
  const identity = session ? `${session.user_id}:${session.role}` : null;
  const currentIdentity = useRef(identity);
  currentIdentity.current = identity;
  const [loadedIdentity, setLoadedIdentity] = useState<string | null>(null);
  const [rows, setRows] = useState<Enquiry[]>([]);
  const [state, setState] = useState<State>("loading");
  const [offset, setOffset] = useState(0);
  const active = useRef<AbortController | null>(null);
  const pending = useRef(false);

  const load = useCallback(async (nextOffset: number) => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    pending.current = true;
    // Never retain the previous page's personal data during a new authorization check.
    setRows([]); setState("loading"); setOffset(nextOffset);
    const requestIdentity = identity;
    if (!requestIdentity) { setState("login"); pending.current = false; return; }
    if (session?.role !== "coordinator") { setState("forbidden"); pending.current = false; return; }
    try {
      const response = await fetch(`/api/user/enquiries?limit=${PAGE_SIZE}&offset=${nextOffset}`, {
        credentials: "same-origin", cache: "no-store", signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      // A response for an old account must not become visible after another-tab login/logout.
      if (currentIdentity.current !== requestIdentity) { setState("login"); return; }
      if (response.status === 401) { setState("login"); return; }
      if (response.status === 403) { setState("forbidden"); return; }
      if (!response.ok) throw new Error("Request failed");
      const data: unknown = await response.json();
      if (!Array.isArray(data) || data.length > PAGE_SIZE || !data.every(isEnquiry)) throw new Error("Invalid list");
      if (controller.signal.aborted) return;
      if (currentIdentity.current !== requestIdentity) { setState("login"); return; }
      // Preserve the API's created_at DESC, id DESC ordering; no browser re-sort.
      setLoadedIdentity(requestIdentity); setRows(data); setState("ready");
    } catch {
      if (!controller.signal.aborted) setState("error");
    } finally {
      if (active.current === controller) pending.current = false;
    }
  }, [identity, session?.role]);

  useEffect(() => {
    void load(0);
    const recheck = () => { void load(0); };
    // Clear/revalidate on tab changes; no polling or session activity refresh is added.
    window.addEventListener("focus", recheck);
    return () => { active.current?.abort(); window.removeEventListener("focus", recheck); };
  }, [load]);

  function navigate(nextOffset: number) {
    if (!pending.current) void load(nextOffset);
  }

  // Hide an old identity's records during render, before effect cleanup runs.
  const displayState = !identity ? "login" : session?.role !== "coordinator" ? "forbidden"
    : state === "ready" && loadedIdentity !== identity ? "loading" : state;

  return <section className={styles.screen} aria-labelledby="enquiries-title">
    <h1 id="enquiries-title">Enquiries</h1>
    {displayState === "login" && <p role="alert">Please log in to view enquiries. <a href="/">Log in</a></p>}
    {displayState === "forbidden" && <p role="alert">You do not have permission</p>}
    {displayState === "loading" && <p role="status">Loading enquiries…</p>}
    {displayState === "error" && <div role="alert"><p>Unable to load enquiries. Please try again.</p><button className="btn" onClick={() => navigate(offset)}>Retry</button></div>}
    {displayState === "ready" && <>
      <p role="status">Page {offset / PAGE_SIZE + 1}. Newest enquiries first.</p>
      {rows.length === 0 && <p>No enquiries on this page.</p>}
      <ul className={styles.list} aria-label="Enquiries">
        {rows.map(row => <li key={row.id} className={styles.card}>
          <h2>{row.name}</h2>
          <dl><dt>Contact</dt><dd>{row.contact}</dd>
            <dt>Message</dt><dd className={styles.message}>{row.message || "No message"}</dd>
            <dt>Submitted</dt><dd><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString()}</time></dd></dl>
        </li>)}
      </ul>
      <nav className={styles.actions} aria-label="Enquiry pages">
        <button className="btn btn-secondary" disabled={offset === 0} onClick={() => navigate(offset - PAGE_SIZE)}>Previous</button>
        <button className="btn" disabled={rows.length < PAGE_SIZE || offset + PAGE_SIZE > MAX_OFFSET} onClick={() => navigate(offset + PAGE_SIZE)}>Next</button>
        <button className="btn btn-secondary" onClick={() => navigate(0)}>Refresh</button>
      </nav>
    </>}
  </section>;
}
