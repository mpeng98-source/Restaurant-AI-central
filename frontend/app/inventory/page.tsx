"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Restaurant = { id: string; name: string; can_review: boolean; can_count: boolean; can_approve: boolean };
type Item = { id: string; sku: string; name: string; base_unit_code: string; storage_zone_id: string | null; units: { code: string; name: string }[] };
type Catalog = { items: Item[]; zones: { id: string; name: string }[] };
type Snapshot = { base_quantity: string; expected_quantity: string | null; variance_quantity: string | null; variance_percentage: string | null; base_unit_code: string; status: string; explanation: string };
type CountLine = { inventory_item_id: string; sku: string; name: string; quantity: string; unit_code: string; note: string | null; snapshot: Snapshot | null };
type CountSession = { id: string; assigned_to: string; storage_zone_id: string | null; status: string; version: number; created_at: string; cutoff_at: string | null; quantity_threshold: string; percentage_threshold: string; lines: CountLine[]; decision?: { action: string; reason: string; decided_at: string } | null };
type Entry = { quantity: string; unit: string; note: string };

function canonicalDecimal(value: string) {
  return value.replace(/^0+(?=\d)/, "").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

async function request<T>(path: string, method = "GET", body?: unknown, csrf = ""): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}/api/v1${path}`, { method, credentials: "include", headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch {
    throw new Error("Connection unavailable. This action has not been confirmed as saved. Reconnect and reload before retrying.");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 409) throw new Error("This session changed in another window or is no longer editable. Reload the latest version before continuing.");
    throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status}). Your changes were not saved.`);
  }
  return response.json() as Promise<T>;
}

export default function InventoryPage() {
  const router = useRouter();
  const [locations, setLocations] = useState<Restaurant[]>([]);
  const [locationId, setLocationId] = useState("");
  const [userId, setUserId] = useState("");
  const [csrf, setCsrf] = useState("");
  const [catalog, setCatalog] = useState<Catalog>({ items: [], zones: [] });
  const [sessions, setSessions] = useState<CountSession[]>([]);
  const [session, setSession] = useState<CountSession | null>(null);
  const [assignees, setAssignees] = useState<{ id: string; name: string }[]>([]);
  const [assignee, setAssignee] = useState("");
  const [zone, setZone] = useState("");
  const [quantityThreshold, setQuantityThreshold] = useState("0");
  const [percentageThreshold, setPercentageThreshold] = useState("5");
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [offline, setOffline] = useState(false);
  const creationKey = useRef<string | null>(null);
  const restaurant = locations.find((location) => location.id === locationId);
  const prefix = `/inventory/locations/${locationId}/count-sessions`;
  const editable = session?.status === "draft" && session.assigned_to === userId;

  useEffect(() => {
    const online = () => setOffline(!navigator.onLine);
    online();
    window.addEventListener("online", online); window.addEventListener("offline", online);
    return () => { window.removeEventListener("online", online); window.removeEventListener("offline", online); };
  }, []);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const me = await fetch(`${apiBase}/api/v1/me`, { credentials: "include" });
      if (me.status === 401) { router.replace("/"); return; }
      if (!me.ok) throw new Error("Your account could not be loaded.");
      const identity = await me.json();
      const choices = await request<Restaurant[]>("/inventory/locations");
      if (!alive) return;
      setUserId(identity.user_id); setCsrf(me.headers.get("X-CSRF-Token") ?? "");
      setLocations(choices); setLocationId(choices[0]?.id ?? ""); setLoading(false);
    })().catch((problem) => { if (alive) { setError(problem.message); setLoading(false); } });
    return () => { alive = false; };
  }, [router]);

  useEffect(() => {
    if (!locationId) return;
    let alive = true;
    setLoading(true); setSession(null); setError(""); setNotice("");
    void (async () => {
      const [nextCatalog, nextSessions] = await Promise.all([
        request<Catalog>(`/inventory/locations/${locationId}/catalog`), request<CountSession[]>(`/inventory/locations/${locationId}/count-sessions`),
      ]);
      const people = restaurant?.can_review ? await request<{ id: string; name: string }[]>(`/inventory/locations/${locationId}/assignees`) : [];
      if (!alive) return;
      setCatalog(nextCatalog); setSessions(nextSessions); setAssignees(people); setAssignee(people[0]?.id ?? userId); setLoading(false);
    })().catch((problem) => { if (alive) { setError(problem.message); setLoading(false); } });
    return () => { alive = false; };
  }, [locationId, restaurant?.can_review, userId]);

  function acceptSession(next: CountSession) {
    setSession(next);
    setEntries(Object.fromEntries(next.lines.map((line) => [line.inventory_item_id, { quantity: line.quantity, unit: line.unit_code, note: line.note ?? "" }])));
    setAssignee(next.assigned_to); setZone(next.storage_zone_id ?? "");
    setQuantityThreshold(next.quantity_threshold); setPercentageThreshold(next.percentage_threshold);
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (problem) { setError(problem instanceof Error ? problem.message : "The request failed. Reload before retrying."); }
    finally { setBusy(false); }
  }

  async function openSession(id: string) {
    await perform(async () => { acceptSession(await request<CountSession>(`${prefix}/${id}`)); });
  }

  async function createSession() {
    await perform(async () => {
      creationKey.current ??= crypto.randomUUID();
      const next = await request<CountSession>(prefix, "POST", { idempotency_key: creationKey.current, ...(restaurant?.can_review ? { assigned_to: assignee, quantity_threshold: quantityThreshold, percentage_threshold: percentageThreshold } : {}), storage_zone_id: zone || null }, csrf);
      creationKey.current = null;
      acceptSession(next); setSessions(await request<CountSession[]>(prefix)); setNotice("Draft session created on the server.");
    });
  }

  function edit(item: Item, patch: Partial<Entry>) {
    setEntries((current) => ({ ...current, [item.id]: { ...(current[item.id] ?? { quantity: "", unit: item.base_unit_code, note: "" }), ...patch } }));
  }

  async function save(item: Item) {
    if (!session) return;
    const entry = entries[item.id];
    if (!entry || !/^\d+(\.\d{1,6})?$/.test(entry.quantity)) { setError("Enter a nonnegative quantity with up to six decimal places."); return; }
    await perform(async () => {
      const next = await request<CountSession>(`${prefix}/${session.id}/lines/${item.id}`, "PUT", { version: session.version, sku: item.sku, quantity: entry.quantity, unit_code: entry.unit, note: entry.note || null }, csrf);
      // Keep other unsaved entries while accepting the server's saved version.
      setSession(next); setNotice(`${item.name} saved. Session version ${next.version}.`);
    });
  }

  async function submit() {
    if (!session) return;
    const hasUnsaved = catalog.items.some((item) => {
      const entry = entries[item.id]; if (!entry) return false;
      const saved = session.lines.find((line) => line.inventory_item_id === item.id);
      if (entry.quantity === "") return Boolean(saved) || entry.note !== "";
      return !saved || canonicalDecimal(entry.quantity) !== canonicalDecimal(saved.quantity) || entry.unit !== saved.unit_code || entry.note !== (saved.note ?? "");
    });
    if (hasUnsaved) { setError("Save each changed item before submitting. Unsaved entries are not included."); return; }
    await perform(async () => {
      acceptSession(await request<CountSession>(`${prefix}/${session.id}/submit`, "POST", { version: session.version }, csrf));
      setSessions(await request<CountSession[]>(prefix)); setNotice("Count submitted and frozen. Stock balances have not changed.");
    });
  }

  async function removeSaved(itemId: string, name: string) {
    if (!session) return;
    await perform(async () => {
      const next = await request<CountSession>(`${prefix}/${session.id}/lines/${itemId}?version=${session.version}`, "DELETE", undefined, csrf);
      setSession(next);
      setEntries((current) => { const copy = { ...current }; delete copy[itemId]; return copy; });
      setNotice(`${name} removed from this draft.`);
    });
  }

  const visibleItems = catalog.items.filter((item) => (!session?.storage_zone_id || item.storage_zone_id === session.storage_zone_id) && `${item.name} ${item.sku}`.toLowerCase().includes(search.toLowerCase()));
  return <main className="inventory-page">
    <header className="workspace-header"><Link className="brand" href="/dashboard">chubby<span className="brand-ai">AI</span></Link><Link href="/dashboard">Workspace</Link></header>
    <div className="inventory-content">
      <p className="eyebrow">INVENTORY / PHYSICAL COUNTS</p><h1>Inventory counts</h1>
      <p className="inventory-muted">Confirm every quantity and unit. Submission sends a frozen count for review.</p>
      {restaurant?.can_approve && <p><Link href="/inventory/approvals">Open inventory approval dashboard →</Link></p>}
      {offline && <p className="inventory-alert" role="alert">You are offline. Counts cannot be saved or submitted. Entries in this window have not been synchronized.</p>}
      {error && <p className="inventory-alert" role="alert">{error} {session && <button onClick={() => openSession(session.id)} disabled={busy}>Reload latest session</button>}</p>}
      {notice && <p className="inventory-notice" role="status">{notice}</p>}
      <label className="inventory-field">Restaurant<select value={locationId} disabled={busy || loading} onChange={(event) => setLocationId(event.target.value)}>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
      {loading && <p role="status">Loading workspace…</p>}
      {!loading && locations.length === 0 && <p className="empty-state">No inventory locations are authorized for this account.</p>}
      {!loading && restaurant && <div className="inventory-layout">
        <aside className="inventory-panel"><h2>Count sessions</h2>
          <ul className="count-session-list">{sessions.map((row) => <li key={row.id}><button disabled={busy} aria-pressed={session?.id === row.id} onClick={() => openSession(row.id)}><strong>{new Date(row.created_at).toLocaleDateString()}</strong><span>{row.status.replaceAll("_", " ")} · v{row.version}</span><small>{assignees.find((person) => person.id === row.assigned_to)?.name ?? (row.assigned_to === userId ? "Assigned to you" : "Assigned counter")}</small></button></li>)}</ul>
          {sessions.length === 0 && <p>No saved sessions yet.</p>}
          <h3>Start a count</h3>
          {restaurant.can_review && <label className="inventory-field">Assigned counter<select aria-label="Assigned counter" value={assignee} onChange={(event) => setAssignee(event.target.value)} disabled={busy}>{assignees.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>}
          <label className="inventory-field">Storage zone<select value={zone} onChange={(event) => setZone(event.target.value)} disabled={busy}><option value="">All zones</option>{catalog.zones.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          {restaurant.can_review && <><label className="inventory-field">Quantity threshold (stock units)<input inputMode="decimal" value={quantityThreshold} onChange={(event) => setQuantityThreshold(event.target.value)} /></label><label className="inventory-field">Variance threshold (%)<input inputMode="decimal" value={percentageThreshold} onChange={(event) => setPercentageThreshold(event.target.value)} /></label></>}
          <button className="inventory-primary" disabled={busy || offline || (restaurant.can_review && !assignee)} onClick={createSession}>Create draft</button>
          {session?.status === "draft" && restaurant.can_review && <button disabled={busy || offline} onClick={() => perform(async () => { acceptSession(await request<CountSession>(`${prefix}/${session.id}`, "PATCH", { version: session.version, assigned_to: assignee, storage_zone_id: zone || null, quantity_threshold: quantityThreshold, percentage_threshold: percentageThreshold }, csrf)); setSessions(await request<CountSession[]>(prefix)); setNotice("Assignment and thresholds updated."); })}>Update selected draft assignment</button>}
        </aside>
        <section className="inventory-panel" aria-labelledby="count-detail-title">
          <h2 id="count-detail-title">{session ? `${session.status.replaceAll("_", " ")} · version ${session.version}` : "Choose or create a count"}</h2>
          {!session && <p>Open a saved session, or create a draft for an assigned employee.</p>}
          {session && <>
            <p>{session.lines.length} confirmed item{session.lines.length === 1 ? "" : "s"}. {session.status === "draft" ? (editable ? "You are the assigned counter." : "Only the assigned employee can enter quantities.") : "This submission is frozen."}</p>
            {session.cutoff_at && <p>Ledger cutoff: {new Date(session.cutoff_at).toLocaleString()}</p>}
            {session.status === "draft" && <>
              <label className="inventory-field">Find an item by name or SKU<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search inventory" /></label>
              {session.lines.filter((line) => !catalog.items.some((item) => item.id === line.inventory_item_id)).map((line) => <article className="count-item" key={line.inventory_item_id}><h3>{line.name}</h3><p>This saved item is no longer enabled in the catalog. Ask a manager to restore it or remove it before submitting.</p><p>Saved: {line.quantity} {line.unit_code}</p>{editable && <button disabled={busy || offline} onClick={() => removeSaved(line.inventory_item_id, line.name)}>Remove unavailable item</button>}</article>)}
              {visibleItems.length === 0 && <p>No matching inventory items are enabled for this location and zone.</p>}
              <div className="count-items">{visibleItems.map((item) => {
                const saved = session.lines.find((line) => line.inventory_item_id === item.id);
                const entry = entries[item.id] ?? { quantity: "", unit: item.base_unit_code, note: "" };
                return <article className="count-item" key={item.id}><h3>{item.name}</h3><p>{item.sku} · Stock unit: {item.base_unit_code}{saved ? " · Saved" : " · Not counted"}</p>
                  <div className="count-entry-row"><label className="inventory-field">Confirmed quantity<input aria-label={`Quantity for ${item.name}`} inputMode="decimal" autoComplete="off" value={entry.quantity} onChange={(event) => edit(item, { quantity: event.target.value })} disabled={!editable || busy || offline} /></label>
                    <label className="inventory-field">Unit<select aria-label={`Unit for ${item.name}`} value={entry.unit} onChange={(event) => edit(item, { unit: event.target.value })} disabled={!editable || busy || offline}>{item.units.map((unit) => <option key={unit.code} value={unit.code}>{unit.name} ({unit.code})</option>)}</select></label></div>
                  <label className="inventory-field">Notes (optional)<textarea maxLength={2000} value={entry.note} onChange={(event) => edit(item, { note: event.target.value })} disabled={!editable || busy || offline} /></label>
                  {editable && <button disabled={busy || offline || !entry.quantity} onClick={() => save(item)}>Save {item.name}</button>}
                  {editable && saved && <button disabled={busy || offline} onClick={() => removeSaved(item.id, item.name)}>Remove saved line</button>}
                </article>;
              })}</div>
              {editable && <div className="count-submit"><p>Check all saved quantities before submission. Submitted entries cannot be edited.</p><button className="inventory-primary" disabled={busy || offline || session.lines.length === 0} onClick={submit}>{busy ? "Saving…" : "Submit confirmed count"}</button></div>}
            </>}
            {session.status !== "draft" && <>
              {session.lines.map((line) => <article className="count-item" key={line.inventory_item_id}><h3>{line.name}</h3><p>{line.sku} · Counted {line.quantity} {line.unit_code}</p>{line.snapshot && <><p><strong>{line.snapshot.status.replaceAll("_", " ")}</strong></p><dl className="variance-values"><div><dt>Expected</dt><dd>{line.snapshot.expected_quantity ?? "Baseline required"} {line.snapshot.expected_quantity !== null && line.snapshot.base_unit_code}</dd></div><div><dt>Confirmed in stock units</dt><dd>{line.snapshot.base_quantity} {line.snapshot.base_unit_code}</dd></div><div><dt>Variance</dt><dd>{line.snapshot.variance_quantity ?? "Unknown"} {line.snapshot.variance_quantity !== null && line.snapshot.base_unit_code}</dd></div><div><dt>Variance %</dt><dd>{line.snapshot.variance_percentage === null ? "Undefined" : `${line.snapshot.variance_percentage}%`}</dd></div></dl><p>At submission: {line.snapshot.explanation}</p></>}</article>)}
              {restaurant.can_review && session.status === "submitted" && <button disabled={busy || offline} onClick={() => perform(async () => { acceptSession(await request<CountSession>(`${prefix}/${session.id}/review`, "POST", { version: session.version }, csrf)); setNotice("Review started. No inventory adjustment has been posted."); })}>Begin GM / owner review</button>}
              {session.decision && <p className="inventory-notice">Report {session.decision.action}: {session.decision.reason}</p>}
              <p className="inventory-muted">Final decisions require an independent authorized reviewer. {restaurant.can_approve && <Link href="/inventory/approvals">Open approval dashboard</Link>}</p>
            </>}
          </>}
        </section>
      </div>}
    </div>
  </main>;
}
