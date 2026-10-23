/* Render the Material 3 login form and call the User Service through Nginx.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { homeFor, type Role } from "@/lib/session";
import { CircularProgress, FilledButton, TextField } from "./material";

type LoginResult = {
  sessionid: string;
  expires_at: string;
  user_id: string;
  instance: string;
  role: Role;
};

export default function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setMessage("");
    setFailed(false);
    try {
      const response = await fetch("/api/user/login", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data: LoginResult | { detail?: unknown } = await response.json();
      if (!response.ok) {
        setFailed(true);
        if (response.status === 401) {
          setMessage("Username or password is incorrect");
        } else if (response.status === 423 && "detail" in data && data.detail && typeof data.detail === "object" && "locked_until" in data.detail) {
          const retry = new Date(String(data.detail.locked_until));
          setMessage(Number.isFinite(retry.getTime())
            ? `Account temporarily locked. Please try again at ${retry.toLocaleString()}.`
            : "Account temporarily locked. Please try again in 10 minutes.");
        } else {
          setMessage("Unable to sign in. Please try again shortly.");
        }
        return;
      }
      const result = data as LoginResult;
      if (!["teacher", "coordinator"].includes(result.role)) throw new Error("Invalid role");
      router.replace(homeFor(result.role));
    } catch {
      setFailed(true);
      setMessage("Unable to sign in. Please try again shortly.");
    } finally {
      setPassword("");
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="panel" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">E</div>
        <p className="eyebrow">ENGLISH LEARNING CLASS</p>
        <h1 id="login-title">Welcome back</h1>
        <p className="subtitle">Sign in to continue your learning journey.</p>
        <form onSubmit={handleLogin} aria-busy={loading}>
          <TextField
            label="Username"
            name="username"
            autocomplete="username"
            required
            disabled={loading}
            value={username}
            onInput={(event) => setUsername((event.target as HTMLInputElement).value)}
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
            disabled={loading}
            value={password}
            onInput={(event) => setPassword((event.target as HTMLInputElement).value)}
          />
          <FilledButton type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </FilledButton>
          {loading && <div className="progress" role="status" aria-label="Signing in">
            <CircularProgress indeterminate aria-hidden="true" />
          </div>}
        </form>
        {message && (
          <p className={`result ${failed ? "error" : "success"}`} role={failed ? "alert" : "status"}>
            {message}
          </p>
        )}
        <p className="note">@Yoobee Inc</p>
      </section>
    </main>
  );
}
