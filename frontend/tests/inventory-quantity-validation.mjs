import assert from "node:assert/strict";
import test from "node:test";

import { countQuantityError } from "../app/inventory/quantity-validation.mjs";

test("count quantities accept zero and up to six decimal places", () => {
  for (const value of ["0", "12", "0.000001", "123.456789"]) {
    assert.equal(countQuantityError(value), null, `${value} should be accepted`);
  }
});

test("count quantities reject empty, negative, exponent, and excessive precision values", () => {
  for (const value of ["", "-1", "1e3", ".5", "1.", "1.0000001", " 2"]) {
    assert.equal(
      countQuantityError(value),
      "Enter a nonnegative quantity with up to six decimal places.",
      `${JSON.stringify(value)} should be rejected`,
    );
  }
});
