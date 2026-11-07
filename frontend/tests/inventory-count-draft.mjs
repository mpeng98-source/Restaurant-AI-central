import assert from "node:assert/strict";
import test from "node:test";

import { countEntryChanged, hasUnsavedCountEntries } from "../app/inventory/count-draft.mjs";

const line = { inventory_item_id: "item-a", quantity: "12.000000", unit_code: "piece", note: null };
const entry = { quantity: "12", unit: "piece", note: "" };

test("decimal formatting does not make a saved count dirty", () => {
  for (const quantity of ["12", "00012", "12.0", "0012.000000"]) {
    assert.equal(countEntryChanged({ ...entry, quantity }, line), false);
  }
  assert.equal(countEntryChanged({ ...entry, quantity: "0" }, { ...line, quantity: "0.000000" }), false);
});

test("quantity, unit, note, and cleared saved counts remain unsaved", () => {
  for (const patch of [{ quantity: "13" }, { quantity: "" }, { quantity: "invalid" }, { quantity: "12." }, { quantity: "12.0000000" }, { unit: "case" }, { note: "Confirm pack size" }]) {
    assert.equal(countEntryChanged({ ...entry, ...patch }, line), true);
  }
});

test("explicit zero without a saved line is unsaved, not an unknown baseline", () => {
  assert.equal(countEntryChanged({ ...entry, quantity: "0" }, undefined), true);
  assert.equal(countEntryChanged({ ...entry, quantity: "" }, undefined), false);
  assert.equal(countEntryChanged({ ...entry, quantity: "", note: "Check later" }, undefined), true);
  assert.equal(countEntryChanged(undefined, line), false);
});

test("large quantities are compared without binary floating-point rounding", () => {
  const saved = { ...line, quantity: "999999999999999999.000001" };
  assert.equal(countEntryChanged({ ...entry, quantity: saved.quantity }, saved), false);
  assert.equal(countEntryChanged({ ...entry, quantity: "999999999999999999.000002" }, saved), true);
});

test("saving one line does not clear other unsaved entries or hide disabled items", () => {
  const entries = { "item-a": entry, "item-b": { ...entry, quantity: "0" } };
  assert.equal(hasUnsavedCountEntries(entries, [line]), true);
  assert.equal(hasUnsavedCountEntries(entries, [line, { ...line, inventory_item_id: "item-b", quantity: "0" }]), false);
  assert.equal(hasUnsavedCountEntries({}, [line]), false);
});
