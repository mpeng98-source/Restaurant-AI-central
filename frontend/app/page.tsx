"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error(response.status === 429 ? "Too many attempts. Try again later." : "Email or password is incorrect.");
      router.push("/dashboard");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Sign-in failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <Link className="brand auth-brand" href="/" aria-label="Chubby AI home"><span className="brand-mark">c</span><span>chubby<span className="brand-ai">AI</span><small>RESTAURANT OPERATIONS</small></span></Link>
        <p className="eyebrow">CHUBBY GROUP</p>
        <h1 id="login-title">Welcome back.</h1>
        <p className="auth-intro">Sign in to your restaurant workspace.</p>
        <form onSubmit={signIn} className="auth-form">
          <label htmlFor="email">Work email</label>
          <input id="email" type="email" autoComplete="username" required maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}<span aria-hidden="true">→</span></button>
        </form>
        <p className="forgot-link"><Link href="/forgot-password">Forgot your password?</Link></p>
        <p className="invite-note">Accounts are invitation only. Contact your organization administrator for access.</p>
        <div className="auth-footer">SECURE ACCESS <span>·</span> CHUBBY GROUP</div>
      </section>
    </main>
  );
}
