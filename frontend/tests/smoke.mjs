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
const inventory = await fetch(`${baseUrl}/inventory`);
assert.equal(inventory.status, 200, "inventory counting route responds");
const inventoryHtml = await inventory.text();
assert.ok(inventoryHtml.includes("Inventory counts"), "inventory page has its accessible page title");
assert.ok(inventoryHtml.includes("Loading workspace"), "inventory page loads authorized workspace data from the API");
assert.ok(!inventoryHtml.includes('type="file"'), "no photo upload control is shown before authorization");
const approvals = await fetch(`${baseUrl}/inventory/approvals`);
assert.equal(approvals.status, 200, "approval dashboard route responds");
assert.ok((await approvals.text()).includes("Inventory approval dashboard"), "approval dashboard has its page title");

const operations = await fetch(`${baseUrl}/inventory/operations`);
assert.equal(operations.status, 200, "pilot operations route responds");
assert.ok((await operations.text()).includes("Opening balances and reconciliation"));
