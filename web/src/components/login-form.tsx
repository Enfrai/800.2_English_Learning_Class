/* Render the Material 3 login form and call the User Service through Nginx.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import { type FormEvent, useState } from "react";
import { CircularProgress, FilledButton, TextField } from "./material";

type LoginResult = {
  sessionid: string;
  expires_at: string;
  user_id: number;
  instance: string;
};

export default function LoginForm() {
  const [username, setUsername] = useState("demo");
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data: LoginResult | { detail?: unknown } = await response.json();
      if (!response.ok) {
        setFailed(true);
        const detail = "detail" in data && typeof data.detail === "string"
          ? data.detail : "Please check your credentials and try again.";
        setMessage(`Login failed (${response.status}): ${detail}`);
        return;
      }
      const result = data as LoginResult;
      setMessage(
        `Login successful! User ID: ${result.user_id}; Instance: ${result.instance}; Expires: ${result.expires_at}`,
      );
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
