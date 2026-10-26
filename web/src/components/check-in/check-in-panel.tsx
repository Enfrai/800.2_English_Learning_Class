/* Show, close and print today's classroom QR check-in using shared Ako controls.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getWindow, openWindow, closeWindow, printWindow, checkinError, LoginRequiredError, type CheckinWindow } from "@/lib/checkin-management-api";
import { formatSessionDate } from "@/lib/dates";
import styles from "./check-in.module.css";
export default function CheckInPanel({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [data, setData] = useState<CheckinWindow | null>(null), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [now, setNow] = useState(Date.now());
  const pending = useRef(false), reading = useRef(0), version = useRef(0);
  const load = useCallback(async () => {
    if (pending.current || reading.current) return;
    const request = ++version.current;
    reading.current = request;
    try { const result = await getWindow(sessionId); if (request === version.current) { setData(result); setError(""); } }
    catch (reason) { if (request !== version.current) return; if (reason instanceof LoginRequiredError) router.replace("/"); else setError(checkinError(reason)); }
    finally { if (reading.current === request) reading.current = 0; }
  }, [sessionId, router]);
  useEffect(() => {
    void load();
    const poll = window.setInterval(() => { if (!document.hidden) void load(); }, 5000);
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { version.current++; reading.current = 0; clearInterval(poll); clearInterval(tick); };
  }, [load]);
  async function change(open: boolean) {
    if (pending.current) return;
    pending.current = true; version.current++; setBusy(true); setError("");
    try { setData(await (open ? openWindow(sessionId) : closeWindow(sessionId))); setNow(Date.now()); }
    catch (reason) { if (reason instanceof LoginRequiredError) router.replace("/"); else setError(checkinError(reason)); }
    finally { pending.current = false; setBusy(false); }
  }
  const expired = data?.state === "open" && data.expires_at && Date.parse(data.expires_at) <= now;
  const open = data?.state === "open" && !expired;
  return <section className={`card no-print ${styles.panel}`} aria-labelledby="qr-heading">
    <h2 id="qr-heading">QR check-in</h2>
    <p>Let learners scan a code and sign in with their names.</p>
    {!data && !error && <p role="status">Loading check-in…</p>}
    {error && <p className="msg msg-error" role="alert">{error} <button className="btn btn-secondary" disabled={busy} onClick={() => void load()}>Retry check-in</button></p>}
    {data && <>
      <p role="status">{open ? "Check-in is open" : expired || data.state === "expired" ? "Check-in has expired" : data.state === "closed" ? "Check-in is closed" : data.state === "unavailable" ? "Close check-in and open it again to display a new code" : "Check-in is not open"}</p>
      {!data.can_open && <p className="hint">Only today's active class can open QR check-in.</p>}
      {open && data.qr_svg && data.sign_in_url && <div className={styles.code}>
        <p>Class date: {formatSessionDate(data.session_date)}</p>
        <img className={styles.qr} src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(data.qr_svg)}`} alt="QR code for class sign-in" width={340} height={340} />
        <p className={styles.link}><a href={data.sign_in_url} target="_blank" rel="noreferrer">{data.sign_in_url}</a></p>
        <p className="hint">The phone must reach this address. Use the same Wi-Fi when running locally.</p>
        <p>Closes at {new Date(data.expires_at!).toLocaleString("en-NZ")}</p>
      </div>}
      <div className="row">
        {!open && data.state !== "unavailable" && <button type="button" className="btn" disabled={busy || !data.can_open} onClick={() => void change(true)}>{busy ? "Opening…" : "Open check-in"}</button>}
        {open && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => { try { printWindow(data); } catch (reason) { setError(checkinError(reason)); } }}>Print QR code</button>}
        {(open || data.state === "unavailable") && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void change(false)}>{busy ? "Closing…" : "Close check-in"}</button>}
      </div>
    </>}
  </section>;
}
