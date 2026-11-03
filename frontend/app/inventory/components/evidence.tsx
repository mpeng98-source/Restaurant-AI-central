"use client";
import { useEffect, useRef, useState } from "react";
const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Evidence = { id: string; object_key: string; retain_until: string; legal_hold: boolean; deleted_at: string | null; scanner_status: string };
async function call(path: string, csrf: string, method = "POST", body?: unknown) {
  const response = await fetch(`${api}${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Evidence action failed");
  return result;
}
export function EvidenceUpload({ locationId, sessionId, csrf, disabled, onUploaded }: { locationId: string; sessionId: string; csrf: string; disabled: boolean; onUploaded: (key: string) => void }) {
  const [status, setStatus] = useState(""); const [busy, setBusy] = useState(false);
  const retry = useRef<{ file: File; id: string } | null>(null);
  const pending = useRef(false);
  async function upload(file: File) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setStatus("");
    try {
      if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 5 * 1024 * 1024) throw new Error("Choose a JPEG or PNG up to 5 MiB. Convert HEIC before uploading.");
      if (retry.current?.file !== file) retry.current = { file, id: crypto.randomUUID() };
      const response = await fetch(`${api}/api/v1/inventory/locations/${locationId}/count-sessions/${sessionId}/evidence?evidence_id=${retry.current.id}`, { method: "POST", credentials: "include", headers: { "Content-Type": file.type, "X-CSRF-Token": csrf }, body: file });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Photo upload failed");
      onUploaded(result.object_key); setStatus("Photo uploaded privately. Save this count line to attach it. Confirm quantity manually."); retry.current = null;
    } catch (error) { setStatus(error instanceof Error ? error.message : "Upload unconfirmed. Reconnect before retrying."); }
    finally { pending.current = false; setBusy(false); }
  }
  return <div className="evidence-controls"><label className="inventory-field">Identification photo (optional)<input aria-label="Identification photo" type="file" accept="image/jpeg,image/png" capture="environment" disabled={disabled || busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} /></label><p>Photos aid identification. Enter and confirm every quantity yourself. No image-based quantity is posted.</p>{retry.current && !busy && <button disabled={disabled} onClick={() => { if (retry.current) void upload(retry.current.file); }}>Retry unconfirmed photo</button>}{status && <p role="status">{status}</p>}</div>;
}

export function EvidencePhoto({ objectKey, locationId, csrf, canManage = false }: { objectKey: string; locationId: string; csrf: string; canManage?: boolean }) {
  const [url, setUrl] = useState(""); const [row, setRow] = useState<Evidence | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [reason, setReason] = useState(""); const [deadline, setDeadline] = useState("");
  const id = objectKey.split("/").at(-1)?.replace(/\.jpg$/, "");
  const prefix = `/api/v1/inventory/locations/${locationId}/evidence/${id}`;
  useEffect(() => {
    if (!url) return;
    const timer = window.setTimeout(() => setUrl(""), 60000);
    const hide = () => { if (document.hidden) setUrl(""); };
    document.addEventListener("visibilitychange", hide);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", hide); URL.revokeObjectURL(url); };
  }, [url]);
  async function view() {
    setBusy(true); setError("");
    try {
      setRow(await call(prefix, csrf, "GET"));
      const grant = await call(`${prefix}/access`, csrf);
      const response = await fetch(`${api}${grant.path}`, { credentials: "include", headers: { "X-Evidence-Token": grant.token } });
      if (!response.ok) throw new Error("Photo expired, revoked, or unavailable. Request a fresh view.");
      setUrl(URL.createObjectURL(await response.blob()));
    } catch (error) { setError(error instanceof Error ? error.message : "Photo unavailable"); }
    finally { setBusy(false); }
  }
  async function control(action: "hold" | "release" | "extend" | "delete") {
    setBusy(true); setError("");
    try {
      if (!reason.trim() || !row) throw new Error("Enter an evidence control reason.");
      if (action === "delete") { await call(`${prefix}/delete`, csrf, "POST", { reason }); setUrl(""); setRow({ ...row, deleted_at: new Date().toISOString() }); }
      else setRow(await call(`${prefix}/retention`, csrf, "PATCH", { reason, legal_hold: action === "hold" ? true : action === "release" ? false : row.legal_hold, ...(action === "extend" ? { retain_until: new Date(deadline).toISOString() } : {}) }));
    } catch (error) { setError(error instanceof Error ? error.message : "Evidence control failed"); }
    finally { setBusy(false); }
  }
  return <div className="evidence-controls"><button disabled={busy} onClick={view}>View protected photo</button>{error && <p role="alert">{error}</p>}{url && <>
    {/* Private object URLs cannot use the Next.js remote image optimizer. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={url} alt="Employee inventory identification evidence; quantity requires human confirmation" className="inventory-evidence-photo" />
    <button onClick={() => setUrl("")}>Hide photo</button></>}
    {row && <p>Retention until {new Date(row.retain_until).toLocaleString()} · {row.legal_hold ? "Legal hold" : "No hold"} · {row.deleted_at ? "Deleted" : "Private"} · {row.scanner_status === "scanned" ? "Scanner completed" : "Sanitized only; pilot scanner sign-off required"}</p>}
    {canManage && row && <><label className="inventory-field">Evidence control reason<input maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} /></label><button disabled={busy || Boolean(row.deleted_at) || !reason.trim()} onClick={() => control(row.legal_hold ? "release" : "hold")}>{row.legal_hold ? "Release evidence hold" : "Place evidence hold"}</button><label className="inventory-field">Extend retention deadline<input type="datetime-local" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label><button disabled={busy || Boolean(row.deleted_at) || !deadline || !reason.trim()} onClick={() => control("extend")}>Extend evidence retention</button><button disabled={busy || row.legal_hold || (!row.deleted_at && new Date(row.retain_until).getTime() > Date.now()) || !reason.trim()} onClick={() => control("delete")}>{row.deleted_at ? "Retry private byte erasure" : "Erase expired photo bytes"}</button></>}
  </div>;
}


export function EvidenceRetentionQueue({ locationId, csrf }: { locationId: string; csrf: string }) {
  const [state, setState] = useState("expired"); const [rows, setRows] = useState<Evidence[]>([]); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true;
    void call(`/api/v1/inventory/locations/${locationId}/evidence?state=${state}&limit=20`, csrf, "GET").then((rows) => { if (active) { setRows(rows); setError(""); } }).catch((error) => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [locationId, csrf, state]);
  async function refresh(more: boolean) { setBusy(true); setError(""); try {
    const next = await call(`/api/v1/inventory/locations/${locationId}/evidence?state=${state}&limit=20&offset=${more ? rows.length : 0}`, csrf, "GET");
    setRows(more ? [...rows, ...next] : next);
  } catch (error) { setError(error instanceof Error ? error.message : "Retention queue unavailable"); } finally { setBusy(false); } }
  return <section className="inventory-panel"><h2>Photo retention review</h2><p>Review expired photos, holds and deletion tombstones. Refresh after each control change. A failed byte erasure must be retried; metadata is never removed.</p><label className="inventory-field">Evidence retention queue<select value={state} disabled={busy} onChange={(event) => setState(event.target.value)}><option value="expired">Expired, ready for reviewed erasure</option><option value="held">Legal holds</option><option value="active">Active retained photos</option><option value="deleted">Deletion tombstones / erasure retries</option></select></label><button disabled={busy} onClick={() => refresh(false)}>Refresh retention queue</button>{error && <p role="alert">{error}</p>}{rows.length === 0 && <p>No evidence in this queue.</p>}{rows.map((row) => <div className="count-item" key={row.id}><p>Evidence {row.id}</p><EvidencePhoto objectKey={row.object_key} locationId={locationId} csrf={csrf} canManage /></div>)}{rows.length > 0 && <button disabled={busy} onClick={() => refresh(true)}>Load more evidence</button>}</section>;
}
