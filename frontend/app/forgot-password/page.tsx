"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [developmentLink, setDevelopmentLink] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/password-reset/request`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
      const result = await response.json();
      setMessage(response.ok ? result.message : "Unable to request a reset. Please try again later.");
      if (response.ok && result.development_token) setDevelopmentLink(`${window.location.origin}/reset-password?token=${encodeURIComponent(result.development_token)}`);
    } catch { setMessage("Unable to reach Chubby AI. Please try again."); }
    finally { setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card"><Link className="brand auth-brand" href="/"><span className="brand-mark">c</span><span>chubby<span className="brand-ai">AI</span><small>RESTAURANT OPERATIONS</small></span></Link><p className="eyebrow">ACCOUNT SECURITY</p><h1>Reset your password.</h1><p className="auth-intro">Enter your work email and we’ll send a single-use reset link.</p><form className="auth-form" onSubmit={submit}><label htmlFor="reset-email">Work email</label><input id="reset-email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={(event) => setEmail(event.target.value)} /><button disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button></form>{message && <p className="auth-result" role="status">{message}</p>}{developmentLink && <p className="invite-note"><a href={developmentLink}>Open development reset link</a></p>}<p className="invite-note"><Link href="/">Return to sign in</Link></p></section></main>;
}
