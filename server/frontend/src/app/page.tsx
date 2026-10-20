/* Provide an interactive login page for the FastAPI User Service.
 * Author: Shuohui Liu
 * Date: 19 Oct 2026
 */

"use client";

import { FormEvent, useState } from "react";

type LoginResult = {
  sessionid: string;
  expires_at: string;
  user_id: number;
  instance: string;
};

export default function Home() {
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const response = await fetch("/api/user/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data: LoginResult | { detail?: string } = await response.json();
      if (!response.ok) {
        setMessage(
          `Login failed (${response.status}): ${"detail" in data ? (data.detail ?? "Unknown error") : "Unknown error"}`,
        );
        return;
      }
      const result = data as LoginResult;
      setMessage(
        `Login successful! User ID: ${result.user_id}; Instance: ${result.instance}; Expires: ${result.expires_at}`,
      );
    } catch {
      setMessage(
        "Unable to reach the login API. Check the containers and Nginx routing.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="panel">
        <h1>ELC Login</h1>
        <p>Sign in English Learning Class services.</p>
        <form onSubmit={handleLogin}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Login"}
          </button>
        </form>
        {message && (
          <p className="result" role="status">
            {message}
          </p>
        )}
        <p className="note">@Yoobee Inc</p>
      </section>
    </main>
  );
}
