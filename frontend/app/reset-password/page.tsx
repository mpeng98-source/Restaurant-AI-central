"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setToken(new URLSearchParams(window.location.search).get("token") ?? ""), []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/password-reset/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, password }) });
      setMessage(response.ok ? "Password updated. Sign in with your new password." : "This reset link is invalid, expired, or the password does not meet requirements.");
    } catch { setMessage("Unable to reach Chubby AI. Please try again."); }
    finally { setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card"><Link className="brand auth-brand" href="/"><span className="brand-mark">c</span><span>chubby<span className="brand-ai">AI</span><small>RESTAURANT OPERATIONS</small></span></Link><p className="eyebrow">ACCOUNT SECURITY</p><h1>Choose a new password.</h1><p className="auth-intro">Use at least 12 characters, including a letter and a number.</p><form className="auth-form" onSubmit={submit}><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} /><button disabled={busy || !token}>{busy ? "Updating…" : "Update password"}</button></form>{message && <p className="auth-result" role="status">{message}</p>}<p className="invite-note"><Link href="/">Return to sign in</Link></p></section></main>;
}
