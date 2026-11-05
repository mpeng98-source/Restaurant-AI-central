import assert from "node:assert/strict";
import test from "node:test";

import { requestInventory } from "../app/inventory/count-request.mjs";

const base = "https://api.tests.example";
const path = "/inventory/locations/location-a/count-sessions/session-a";

test("count reads keep session credentials and do not send a mutation body or CSRF token", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, `${base}/api/v1${path}`);
    assert.deepEqual(options, { method: "GET", credentials: "include", headers: { "Content-Type": "application/json" } });
    return Response.json({ version: 2 });
  });
  assert.deepEqual(await requestInventory(base, path), { version: 2 });
  assert.equal(fetch.mock.callCount(), 1);
});

test("count mutations retain exact decimal strings, version and CSRF protection", async (t) => {
  const body = { version: 2, quantity: "999999999999999999.000001", unit_code: "piece" };
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options.method, "PUT");
    assert.equal(options.credentials, "include");
    assert.equal(options.headers["X-CSRF-Token"], "synthetic-csrf");
    assert.equal(options.body, JSON.stringify(body));
    return Response.json({ version: 3 });
  });
  assert.deepEqual(await requestInventory(base, path, "PUT", body, "synthetic-csrf"), { version: 3 });
});

test("DELETE requests carry CSRF but omit an undefined body", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options.method, "DELETE");
    assert.equal(options.headers["X-CSRF-Token"], "synthetic-csrf");
    assert.equal("body" in options, false);
    return Response.json({ version: 3 });
  });
  await requestInventory(base, path, "DELETE", undefined, "synthetic-csrf");
});

test("network failure during a mutation is uncertain and is never automatically retried", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Connection lost"); });
  await assert.rejects(requestInventory(base, path, "POST", { version: 2 }), /not been confirmed as saved.*server may already have saved it/);
  assert.equal(fetch.mock.callCount(), 1);
});

test("network failure during a read requests reload without asserting a stock change", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Offline"); });
  await assert.rejects(requestInventory(base, path), /Reconnect and reload to retrieve the latest server state/);
});

test("expired sign-in explicitly preserves entries and requires sign-in then reload", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Unauthorized" }, { status: 401 }));
  await assert.rejects(requestInventory(base, path, "PUT", { version: 2 }), /sign-in session has expired.*not been cleared.*Sign in again.*reload/);
});

test("version conflicts preserve entries and require the latest server version", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Stale version" }, { status: 409 }));
  await assert.rejects(requestInventory(base, path, "POST", { version: 2 }), /changed in another window.*not been cleared.*Reload/);
});

test("server failures cannot claim a mutation was not saved, even with a JSON error", async (t) => {
  for (const status of [500, 502, 503, 504]) {
    t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Internal server error" }, { status }));
    await assert.rejects(requestInventory(base, path, "PUT", { version: 2 }), /not been confirmed as saved.*server may already have saved it/);
  }
});

test("failed reads report failure without a false mutation result", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("Proxy failure", { status: 502 }));
  await assert.rejects(requestInventory(base, path), /Server request failed \(502\).*Reload to retrieve/);
});

test("malformed successful mutation responses remain uncertain instead of returning success", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("Not JSON", { status: 200 }));
  await assert.rejects(requestInventory(base, path, "PUT", { version: 2 }), /response could not be read.*not been confirmed as saved/);
});

test("interrupted response bodies remain uncertain", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(new ReadableStream({
    start(controller) { controller.error(new Error("Interrupted")); },
  })));
  await assert.rejects(requestInventory(base, path, "PUT", { version: 2 }), /response could not be read.*server may already have saved it/);
});

test("empty success responses fail explicitly when a count-session response is required", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 204 }));
  await assert.rejects(requestInventory(base, path, "DELETE"), /response could not be read.*not been confirmed as saved/);
});

test("malformed successful reads request reload without returning a default", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("Not JSON"));
  await assert.rejects(requestInventory(base, path), /response could not be read.*Reload to retrieve/);
});

test("validation and permission denials retain the API's error detail", async (t) => {
  for (const status of [400, 403, 422]) {
    t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Location permission denied" }, { status }));
    await assert.rejects(requestInventory(base, path, "PUT"), { message: "Location permission denied" });
  }
});

test("HTML, null, and structured rejection bodies fail explicitly without type errors", async (t) => {
  for (const body of ["Proxy rejected request", "null", JSON.stringify({ detail: [{ msg: "Invalid quantity" }] })]) {
    t.mock.method(globalThis, "fetch", async () => new Response(body, { status: 403 }));
    await assert.rejects(requestInventory(base, path, "PUT"), /Request rejected \(403\).*not been cleared/);
  }
});
