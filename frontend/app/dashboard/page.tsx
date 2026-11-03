"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Identity = { email: string; employee: { first_name: string; last_name: string } | null; assignments: Array<{ role: string; permissions: string[] }> };
type Location = { id: string; name: string; code: string };

function csrfCookie() {
  return document.cookie.split("; ").find((part) => part.startsWith("chubby_csrf="))?.split("=").slice(1).join("=") ?? "";
}

export default function DashboardPage() {
  const router = useRouter();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [error, setError] = useState("");
  const [csrfToken, setCsrfToken] = useState("");
  useEffect(() => {
    let alive = true;
    void (async () => {
      const [meResponse, locationsResponse] = await Promise.all([
        fetch(`${apiBase}/api/v1/me`, { credentials: "include" }),
        fetch(`${apiBase}/api/v1/locations`, { credentials: "include" }),
      ]);
      if (!alive) return;
      if (meResponse.status === 401) { router.replace("/"); return; }
      if (!meResponse.ok || !locationsResponse.ok) { setError("Your workspace could not be loaded."); return; }
      setIdentity(await meResponse.json());
      setCsrfToken(meResponse.headers.get("X-CSRF-Token") ?? "");
      setLocations(await locationsResponse.json());
    })().catch(() => alive && setError("Unable to reach Chubby AI. Please try again."));
    return () => { alive = false; };
  }, [router]);

  async function signOut() {
    const response = await fetch(`${apiBase}/api/v1/auth/logout`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrfToken || decodeURIComponent(csrfCookie()) } });
    if (response.ok) router.replace("/");
    else setError("Sign out failed. Please reload and try again.");
  }

  const roles = [...new Set(identity?.assignments.map((assignment) => assignment.role) ?? [])];
  return <main className="workspace-page">
    <header className="workspace-header"><Link className="brand" href="/dashboard"><span className="brand-mark">c</span><span>chubby<span className="brand-ai">AI</span><small>RESTAURANT OPERATIONS</small></span></Link><button className="signout-button" onClick={signOut}>Sign out</button></header>
    <section className="workspace-content">
      <p className="eyebrow"><i className="status-dot" /> CHUBBY GROUP <span className="eyebrow-divider">/</span> WORKSPACE</p>
      <h1>Welcome{identity?.employee ? `, ${identity.employee.first_name}` : ""}.</h1>
      <p className="auth-intro">{identity?.email ?? "Loading your account…"}{roles.length > 0 ? ` · ${roles.join(", ")}` : ""}</p>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <p><Link href="/inventory">Open inventory counts →</Link></p>
      <div className="workspace-title"><h2>Your locations</h2><span>{locations.length} assigned</span></div>
      {locations.length > 0 ? <ul className="location-list">{locations.map((location) => <li key={location.id}><span className="location-icon">⌂</span><span><strong>{location.name}</strong><small>{location.code}</small></span><span className="location-status"><i /> Active</span></li>)}</ul> : <p className="empty-state">{identity ? "No locations are assigned to this account." : "Loading locations…"}</p>}
      <p className="workspace-note">Location access is checked by the server for every request.</p>
    </section>
  </main>;
}
