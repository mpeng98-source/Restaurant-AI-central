"use client";

import Link from "next/link";
import { EvidencePhoto } from "../components/evidence";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Place = { id: string; name: string; can_approve: boolean };
type Snapshot = { base_quantity: string; base_unit_code: string; expected_quantity: string | null; variance_quantity: string | null; variance_percentage: string | null; status: string; explanation: string };
type Line = { id: string; sku: string; name: string; counted_by: string; quantity: string; unit_code: string; note: string | null; photo_object_key: string | null; snapshot: Snapshot };
type Movement = { id: string; count_line_id: string; movement_type: string; quantity_delta: string; unit_code: string; balance_before: string; balance_after: string; reason: string; actor_id: string; audit_log_id: string; created_at: string; can_reverse: boolean; reversed: boolean };
type Report = { id: string; status: string; version: number; assigned_to: string; cutoff_at: string; lines: Line[]; snapshot_hash: string; can_approve: boolean; can_reject: boolean; four_eyes_blocked: boolean; counters: { id: string; name: string | null }[]; decision: { id: string; action: string; reason: string; decided_by: string; decided_at: string; audit_log_id: string; reviewed_lines: { line_id: string; verdict: string }[] } | null; movements: Movement[]; approval_blockers: { baseline_required_lines: string[]; ledger_changed_items: string[]; counter_assignment_changed: boolean } };
type ReversalPreview = { movement_id: string; expected_balance: string; quantity_delta: string; balance_after: string; unit_code: string };
const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function api<T>(path: string, method = "GET", body?: unknown, csrf = ""): Promise<T> {
  let response: Response;
  try { response = await fetch(`${apiBase}/api/v1/inventory${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }); }
  catch { throw new Error("Connection unavailable. This decision is not confirmed. Reconnect and reload before retrying."); }
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(`${response.status === 409 ? "Conflict: " : ""}${typeof error.detail === "string" ? error.detail : `Request failed (${response.status})`}`); }
  return response.json() as Promise<T>;
}

export default function ApprovalsPage() {
  const router = useRouter();
  const [places, setPlaces] = useState<Place[]>([]);
  const [location, setLocation] = useState("");
  const [filter, setFilter] = useState("pending");
  const [reports, setReports] = useState<Report[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [csrf, setCsrf] = useState("");
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<ReversalPreview | null>(null);
  const [correctionReason, setCorrectionReason] = useState("");
  const [correctionConfirmed, setCorrectionConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const requestKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const correctionKey = useRef<{ fingerprint: string; key: string } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const base = `/locations/${location}`;

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine); update();
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  useEffect(() => {
    let alive = true;
    void (async () => {
      const identity = await fetch(`${apiBase}/api/v1/me`, { credentials: "include" });
      if (identity.status === 401) { router.replace("/"); return; }
      if (!identity.ok) throw new Error("Unable to load your account.");
      const locations = (await api<Place[]>("/locations")).filter((place) => place.can_approve);
      if (alive) { setPlaces(locations); setLocation(locations[0]?.id ?? ""); setCsrf(identity.headers.get("X-CSRF-Token") ?? ""); setLoading(false); }
    })().catch((problem) => { if (alive) { setError(problem.message); setLoading(false); } });
    return () => { alive = false; };
  }, [router]);
  useEffect(() => {
    if (!location) return;
    let alive = true;
    setLoading(true); setReport(null); setPreview(null); setError(""); setNotice("");
    void api<Report[]>(`/locations/${location}/approval-dashboard?state=${filter}`).then((rows) => { if (alive) { setReports(rows); setLoading(false); } }).catch((problem) => { if (alive) { setError(problem.message); setLoading(false); } });
    return () => { alive = false; };
  }, [location, filter]);

  function accept(next: Report) {
    setReport(next); setChoices(Object.fromEntries(next.decision?.reviewed_lines.map((line) => [line.line_id, line.verdict]) ?? []));
    setReason(""); setConfirmed(false); setPreview(null); setCorrectionReason(""); setCorrectionConfirmed(false);
  }
  async function perform(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (problem) { setError(problem instanceof Error ? problem.message : "Request failed. Reload before retrying."); }
    finally { busyRef.current = false; setBusy(false); }
  }
  async function open(id: string) { await perform(async () => { accept(await api<Report>(`${base}/count-sessions/${id}`)); }); }
  async function refreshList() { setReports(await api<Report[]>(`${base}/approval-dashboard?state=${filter}`)); }
  async function loadOlder() { await perform(async () => { const rows = await api<Report[]>(`${base}/approval-dashboard?state=${filter}&offset=${reports.length}`); setReports((current) => [...current, ...rows]); }); }
  async function decide(action: "approved" | "rejected") {
    if (!report) return;
    const reviewed = report.lines.map((line) => ({ line_id: line.id, verdict: choices[line.id] })).sort((a, b) => a.line_id.localeCompare(b.line_id));
    const payload = { version: report.version, snapshot_hash: report.snapshot_hash, action, reason: reason.trim(), reviewed_lines: reviewed };
    const fingerprint = JSON.stringify({ report: report.id, ...payload });
    if (requestKey.current?.fingerprint !== fingerprint) requestKey.current = { fingerprint, key: crypto.randomUUID() };
    const key = requestKey.current.key;
    await perform(async () => {
      const next = await api<Report>(`${base}/count-sessions/${report.id}/decision`, "POST", { ...payload, idempotency_key: key }, csrf);
      accept(next); requestKey.current = null;
      setNotice(action === "approved" ? "Report approved. All eligible nonzero adjustments were posted exactly once." : "Report rejected. No stock movements were posted; create a fresh count if needed.");
      await refreshList();
    });
  }
  async function reverse() {
    if (!preview) return;
    const payload = { reason: correctionReason.trim(), expected_balance: preview.expected_balance };
    const fingerprint = JSON.stringify({ movement: preview.movement_id, ...payload });
    if (correctionKey.current?.fingerprint !== fingerprint) correctionKey.current = { fingerprint, key: crypto.randomUUID() };
    const key = correctionKey.current.key;
    await perform(async () => {
      accept(await api<Report>(`${base}/movements/${preview.movement_id}/reverse`, "POST", { ...payload, idempotency_key: key }, csrf));
      correctionKey.current = null; setNotice("Compensating reversal posted. The original adjustment remains immutable.");
      await refreshList();
    });
  }
  const allReviewed = Boolean(report?.lines.length) && report!.lines.every((line) => ["accepted", "disputed"].includes(choices[line.id]));
  const anyDisputed = report?.lines.some((line) => choices[line.id] === "disputed") ?? false;
  const canConfirm = allReviewed && reason.trim().length > 0 && confirmed && !busy && !offline;
  return <main className="inventory-page">
    <header className="workspace-header"><Link className="brand" href="/dashboard">chubby<span className="brand-ai">AI</span></Link><Link href="/inventory">Inventory counts</Link></header>
    <div className="inventory-content"><p className="eyebrow">INVENTORY / HUMAN REVIEW</p><h1>Inventory approval dashboard</h1><p className="inventory-muted">Review every frozen line. Approval posts immutable adjustments; rejection posts none.</p>
      {offline && <p className="inventory-alert" role="alert">You are offline. Decisions and corrections cannot be submitted.</p>}
      {error && <p className="inventory-alert" role="alert">{error} {report && <button disabled={busy} onClick={() => open(report.id)}>Reload latest report</button>}</p>}
      {notice && <p className="inventory-notice" role="status">{notice}</p>}
      <div className="count-entry-row"><label className="inventory-field">Restaurant<select value={location} disabled={busy || loading} onChange={(event) => setLocation(event.target.value)}>{places.map((place) => <option key={place.id} value={place.id}>{place.name}</option>)}</select></label><label className="inventory-field">Report status<select value={filter} disabled={busy} onChange={(event) => setFilter(event.target.value)}><option value="pending">Pending review</option><option value="reviewed">Approved / rejected</option><option value="all">All submitted reports</option></select></label></div>
      {loading && <p role="status">Loading approval workspace…</p>}
      {!loading && places.length === 0 && <p>No locations grant this account inventory approval permission.</p>}
      {!loading && location && <div className="inventory-layout">
        <aside className="inventory-panel"><h2>Count reports</h2><ul className="count-session-list">{reports.map((row) => <li key={row.id}><button disabled={busy} aria-pressed={report?.id === row.id} onClick={() => open(row.id)}><strong>{row.status.replaceAll("_", " ")}</strong><span>{new Date(row.cutoff_at).toLocaleString()}</span><small>Report {row.id.slice(0, 8)} · v{row.version}</small></button></li>)}</ul>{reports.length === 0 && <p>No reports match this filter.</p>}{reports.length >= 50 && <button disabled={busy} onClick={loadOlder}>Load older reports</button>}</aside>
        <section className="inventory-panel" aria-labelledby="approval-detail-title"><h2 id="approval-detail-title">{report ? `Report ${report.id.slice(0, 8)} · ${report.status.replaceAll("_", " ")}` : "Choose a report"}</h2>
          {report && <><p>Cutoff: {new Date(report.cutoff_at).toLocaleString()} · Version {report.version}</p><p>Counter identities: {report.counters?.map((counter) => `${counter.name ?? "Assigned counter"} (${counter.id})`).join(", ")}</p>
            {report.four_eyes_blocked && <p className="inventory-alert" role="alert">Four-eyes control: you counted this report. A different authorized GM or Owner must decide or correct it.</p>}
            {report.status === "submitted" && <button disabled={busy || offline} onClick={() => perform(async () => { accept(await api<Report>(`${base}/count-sessions/${report.id}/review`, "POST", { version: report.version }, csrf)); await refreshList(); setNotice("Report is under review. Confirm every line before deciding."); })}>Begin review</button>}
            {report.status === "under_review" && <div>{report.approval_blockers.baseline_required_lines.length > 0 && <p className="inventory-alert">Baseline required: approval is blocked. Reject and initialize stock before a fresh count.</p>}{report.approval_blockers.ledger_changed_items.length > 0 && <p className="inventory-alert">Ledger activity occurred after submission. Approval is blocked; perform a fresh count or reconcile first.</p>}{report.approval_blockers.counter_assignment_changed && <p className="inventory-alert">A counter assignment changed. Approval requires a fresh count.</p>}</div>}
            {report.lines.map((line) => <article className="count-item" key={line.id}><h3>{line.name}</h3><p>{line.sku} · Counted by {report.counters?.find((counter) => counter.id === line.counted_by)?.name ?? line.counted_by}</p><dl className="variance-values"><div><dt>Expected stock</dt><dd>{line.snapshot.expected_quantity ?? "Baseline required"} {line.snapshot.expected_quantity !== null && line.snapshot.base_unit_code}</dd></div><div><dt>Physical count</dt><dd>{line.quantity} {line.unit_code} → {line.snapshot.base_quantity} {line.snapshot.base_unit_code}</dd></div><div><dt>Variance quantity</dt><dd>{line.snapshot.variance_quantity ?? "Unknown"} {line.snapshot.variance_quantity !== null && line.snapshot.base_unit_code}</dd></div><div><dt>Variance percentage</dt><dd>{line.snapshot.variance_percentage === null ? "Undefined" : `${line.snapshot.variance_percentage}%`}</dd></div></dl><p>{line.snapshot.status.replaceAll("_", " ")} · At submission: {line.snapshot.explanation}</p><p>Counter notes: {line.note || "None"}</p><p>Identification evidence: {line.photo_object_key ? "Protected photo attached" : "No photo attached"}</p>{line.photo_object_key && <EvidencePhoto objectKey={line.photo_object_key} locationId={location} csrf={csrf} canManage />}
              {report.status === "under_review" && <label className="inventory-field">Review {line.sku}<select aria-label={`Review ${line.sku}`} value={choices[line.id] ?? ""} disabled={busy || report.four_eyes_blocked} onChange={(event) => { setChoices((current) => ({ ...current, [line.id]: event.target.value })); setConfirmed(false); }}><option value="">Choose a line decision</option><option value="accepted">Accepted — count confirmed</option><option value="disputed">Disputed — recount required</option></select></label>}
            </article>)}
            {report.status === "under_review" && <div className="approval-decision"><h3>Decision for the complete report</h3><p>Approval requires every line to be accepted. Rejection closes the entire report, including accepted lines, and posts no stock movements.</p><label className="inventory-field">Decision reason<textarea value={reason} maxLength={2000} disabled={busy || report.four_eyes_blocked} onChange={(event) => { setReason(event.target.value); setConfirmed(false); }} /></label><label className="approval-confirm"><input type="checkbox" checked={confirmed} disabled={busy || report.four_eyes_blocked} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed the frozen quantities, units, counters, cutoff and every line decision.</label><div className="approval-actions"><button className="inventory-primary" disabled={!canConfirm || anyDisputed || !report.can_approve} onClick={() => decide("approved")}>Approve and post adjustments</button><button disabled={!canConfirm || !anyDisputed || !report.can_reject} onClick={() => decide("rejected")}>Reject complete report</button></div></div>}
            {report.decision && <div className="inventory-notice"><h3>Report {report.decision.action}</h3><p>{report.decision.reason}</p><p>Reviewer: {report.decision.decided_by} · {new Date(report.decision.decided_at).toLocaleString()}</p><small>Decision {report.decision.id} · Audit {report.decision.audit_log_id}</small></div>}
            {report.movements?.map((movement) => <article className="count-item" key={movement.id}><h3>{movement.movement_type === "reversal" ? "Compensating reversal" : "Posted count adjustment"}{movement.reversed ? " — reversed" : ""}</h3><p data-testid="movement-balance">{movement.quantity_delta} {movement.unit_code} · Balance {movement.balance_before} → {movement.balance_after}</p><p>{movement.reason}</p><small>Movement {movement.id} · Audit {movement.audit_log_id}</small>{movement.can_reverse && <p><button disabled={busy || offline} onClick={() => perform(async () => { setPreview(await api<ReversalPreview>(`${base}/movements/${movement.id}/reversal-preview`)); setCorrectionReason(""); setCorrectionConfirmed(false); })}>Preview compensating reversal</button></p>}</article>)}
            {preview && <div className="approval-decision"><h3>Confirm a compensating reversal</h3><p>This adds {preview.quantity_delta} {preview.unit_code} to the current balance {preview.expected_balance}, producing {preview.balance_after}. The original movement remains unchanged.</p><label className="inventory-field">Correction reason<textarea value={correctionReason} maxLength={2000} onChange={(event) => { setCorrectionReason(event.target.value); setCorrectionConfirmed(false); }} /></label><label className="approval-confirm"><input type="checkbox" checked={correctionConfirmed} onChange={(event) => setCorrectionConfirmed(event.target.checked)} />I confirm the displayed current balance and compensating movement.</label><button disabled={busy || offline || !correctionConfirmed || !correctionReason.trim()} onClick={reverse}>Post compensating reversal</button></div>}
          </>}
        </section>
      </div>}
    </div>
  </main>;
}
