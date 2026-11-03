import assert from "node:assert/strict";

const baseUrl = process.env.BASE_URL ?? "http://localhost:3000";
const response = await fetch(baseUrl);
assert.equal(response.status, 200, "home page responds successfully");
const html = await response.text();
for (const text of ["Welcome back.", "Work email", "Sign in", "Accounts are invitation only"]) {
  assert.ok(html.includes(text), `login page includes ${text}`);
}
const dashboard = await fetch(`${baseUrl}/dashboard`);
assert.equal(dashboard.status, 200, "dashboard route responds and defers identity authorization to API");
console.log("frontend smoke test passed");
