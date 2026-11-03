"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export default function AcceptInvitationPage() {
  const [token, setToken] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setToken(new URLSearchParams(window.location.search).get("token") ?? ""), []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/invitations/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, first_name: firstName, last_name: lastName, password }) });
      setMessage(response.ok ? "Your account is ready. You can now sign in." : "This invitation is invalid, expired, or the password does not meet requirements.");
    } catch { setMessage("Unable to reach Chubby AI. Please try again."); }
    finally { setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card"><Link className="brand auth-brand" href="/"><span className="brand-mark">c</span><span>chubby<span className="brand-ai">AI</span><small>RESTAURANT OPERATIONS</small></span></Link><p className="eyebrow">INVITED ACCOUNT</p><h1>Join your workspace.</h1><p className="auth-intro">Create your account using the details your organization provided.</p><form className="auth-form" onSubmit={submit}><label htmlFor="first-name">First name</label><input id="first-name" autoComplete="given-name" required maxLength={100} value={firstName} onChange={(event) => setFirstName(event.target.value)} /><label htmlFor="last-name">Last name</label><input id="last-name" autoComplete="family-name" required maxLength={100} value={lastName} onChange={(event) => setLastName(event.target.value)} /><label htmlFor="invite-password">Password</label><input id="invite-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} /><button disabled={busy || !token}>{busy ? "Creating account…" : "Accept invitation"}</button></form>{message && <p className="auth-result" role="status">{message}</p>}<p className="invite-note"><Link href="/">Return to sign in</Link></p></section></main>;
}
