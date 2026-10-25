"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { clearSessionId, homeFor, readSession, type Session } from "@/lib/session";

import { SessionContext } from "./session-context";

const LogoutButton = dynamic(() => import("./logout-button"), { ssr: false });

/**
 * `layout="kit"` is for the (staff) pages styled with the Ako UI kit: the navy
 * menu bar from UI design document section 4. The default keeps the panel
 * layout of the (auth) pages, which load the Material styles instead.
 */
export default function SessionShell({
  children,
  layout = "panel",
}: {
  children: ReactNode;
  layout?: "panel" | "kit";
}) {
  const router = useRouter();
  const path = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  const logoutAction = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    let disposed = false;
    let ended = false;
    let loggingOut = false;
    let refreshing = false;
    let dirty = false;
    let deadline = 0;
    let activityTimer: ReturnType<typeof setTimeout> | undefined;
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("ako-session") : null;

    const end = (broadcast = false) => {
      if (ended || disposed) return;
      ended = true;
      clearSessionId();
      setSession(null);
      clearTimeout(activityTimer);
      clearTimeout(expiryTimer);
      if (broadcast) channel?.postMessage("logout");
      router.replace("/");
    };
    const scheduleExpiry = (expiresAt: number) => {
      deadline = expiresAt;
      clearTimeout(expiryTimer);
      expiryTimer = setTimeout(() => end(), Math.max(0, expiresAt - Date.now()));
    };
    const check = async () => {
      if (ended || disposed || loggingOut) return;
      try {
        const current = await readSession();
        if (ended || disposed || loggingOut) return;
        if (!current || current.expiresAt <= Date.now()) return end();
        setSession(current);
        setError("");
        scheduleExpiry(current.expiresAt);
      } catch (reason) {
        if (!disposed && !ended) setError(reason instanceof Error ? reason.message : "Unable to check your session.");
      }
    };
    const refresh = async () => {
      if (!dirty || refreshing || ended || disposed || loggingOut) return;
      if (deadline && deadline <= Date.now()) return end();
      dirty = false;
      refreshing = true;
      try {
        const response = await fetch("/api/user/activity", { method: "POST", credentials: "same-origin", cache: "no-store" });
        if (ended || disposed || loggingOut) return;
        if (response.status === 401) return end(true);
        if (!response.ok) throw new Error("Unable to update your session. Please try again.");
        const data = await response.json();
        const expiresAt = Date.parse(data.expires_at);
        if (!Number.isFinite(expiresAt)) throw new Error("Unable to verify your session.");
        scheduleExpiry(expiresAt);
        channel?.postMessage("activity");
        setError("");
      } catch (reason) {
        if (!disposed && !ended) setError(reason instanceof Error ? reason.message : "Unable to update your session.");
      } finally {
        refreshing = false;
        if (dirty && !ended && !disposed && !loggingOut) activityTimer = setTimeout(refresh, 250);
      }
    };
    const interacted = (event: Event) => {
      if (!event.isTrusted || ended || loggingOut || !deadline) return;
      if (deadline <= Date.now()) return end();
      dirty = true;
      clearTimeout(activityTimer);
      if (!refreshing) void refresh();
    };
    const visible = () => {
      if (document.visibilityState === "visible") void check();
    };
    const restored = () => void check();
    channel && (channel.onmessage = (event) => {
      if (event.data === "logout") end();
      else if (event.data === "activity") void check();
    });
    logoutAction.current = async () => {
      if (loggingOut || ended) return;
      loggingOut = true;
      setLeaving(true);
      clearTimeout(activityTimer);
      dirty = false;
      try {
        const response = await fetch("/api/user/logout", { method: "POST", credentials: "same-origin", cache: "no-store" });
        if (response.ok || response.status === 401) end(true);
        else throw new Error("Unable to log out. Please try again.");
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "Unable to log out.");
      } finally {
        loggingOut = false;
        if (!disposed) setLeaving(false);
      }
    };
    void check();
    // Polling observes the server; only trusted input events call /activity.
    const poll = setInterval(check, 30_000);
    window.addEventListener("pointerdown", interacted);
    window.addEventListener("keydown", interacted);
    window.addEventListener("pageshow", restored);
    window.addEventListener("focus", restored);
    document.addEventListener("visibilitychange", visible);
    return () => {
      disposed = true;
      clearInterval(poll);
      clearTimeout(activityTimer);
      clearTimeout(expiryTimer);
      channel?.close();
      window.removeEventListener("pointerdown", interacted);
      window.removeEventListener("keydown", interacted);
      window.removeEventListener("pageshow", restored);
      window.removeEventListener("focus", restored);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [router]);

  if (!session) return <main className="page"><p role={error ? "alert" : "status"}>{error || "Checking your session…"}</p></main>;
  const home = homeFor(session.role);
  const denied = (path.startsWith("/account-management") || path.startsWith("/coordinator") || path.startsWith("/enquiries")) && session.role !== "coordinator"
    || path.startsWith("/teacher") && session.role !== "teacher";
  if (layout === "kit") {
    // A section stays current on its sub-pages, e.g. a session's attendance.
    const current = (href: string) =>
      (href === home ? path === home : path.startsWith(href)) ? "page" : undefined;
    return <>
      <header className="bar">
        <Link className="logo" href={home}>Ako</Link>
        <nav aria-label={session.role === "teacher" ? "Teacher menu" : "Coordinator menu"}>
          <Link href={home} aria-current={current(home)}>Home</Link>
          <Link href="/sessions" aria-current={current("/sessions")}>Class sessions</Link>
          <Link href="/learners" aria-current={current("/learners")}>Learners</Link>
          <Link href="/lessons" aria-current={current("/lessons")}>Lessons</Link>
          {session.role === "coordinator" && <Link href="/enquiries" aria-current={path === "/enquiries" ? "page" : undefined}>Enquiries</Link>}
          {session.role === "coordinator" && <Link href="/account-management">Account management</Link>}
        </nav>
        <div className="who">
          {session.display_name} ({session.role}) ·{" "}
          <button type="button" className="btn btn-secondary" disabled={leaving} onClick={() => void logoutAction.current()}>
            {leaving ? "Logging out…" : "Log out"}
          </button>
        </div>
      </header>
      <main className="page">
        {error && <div className="msg msg-error" role="alert">{error}</div>}
        {denied ? <div className="msg msg-error" role="alert">You do not have permission</div> : <SessionContext.Provider value={session}>{children}</SessionContext.Provider>}
      </main>
    </>;
  }
  return <main className="page"><section className="panel home-panel">
    <nav aria-label={session.role === "teacher" ? "Teacher menu" : "Coordinator menu"}>
      <Link href={home} aria-current={path === home ? "page" : undefined}>Home</Link>
      <Link href="/learners">Learners</Link>
      <Link href="/sessions">Class sessions</Link>
      <Link href="/lessons">Lessons</Link>
      {session.role === "coordinator" && <Link href="/enquiries" aria-current={path === "/enquiries" ? "page" : undefined}>Enquiries</Link>}
      {session.role === "coordinator" && <Link href="/account-management" aria-current={path === "/account-management" ? "page" : undefined}>Account management</Link>}
      <LogoutButton disabled={leaving} onClick={() => void logoutAction.current()} />
    </nav>
    {error && <p className="result error" role="alert">{error}</p>}
    {denied ? <p role="alert">You do not have permission</p> : <SessionContext.Provider value={session}>{children}</SessionContext.Provider>}
  </section></main>;
}
