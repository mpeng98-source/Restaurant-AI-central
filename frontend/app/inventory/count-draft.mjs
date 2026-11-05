function canonicalDecimal(value) {
  return value.replace(/^0+(?=\d)/, "").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

export function countEntryChanged(entry, saved) {
  if (!entry) return false;
  if (entry.quantity === "") return Boolean(saved) || entry.note !== "" || Boolean(entry.photo);
  return Boolean(countQuantityError(entry.quantity)) || !saved
    || canonicalDecimal(entry.quantity) !== canonicalDecimal(saved.quantity)
    || entry.unit !== saved.unit_code
    || entry.note !== (saved.note ?? "")
    || (entry.photo ?? "") !== (saved.photo_object_key ?? "");
}

export function hasUnsavedCountEntries(entries, lines) {
  const saved = new Map(lines.map((line) => [line.inventory_item_id, line]));
  return Object.entries(entries).some(([id, entry]) => countEntryChanged(entry, saved.get(id)));
}
import { countQuantityError } from "./quantity-validation.mjs";
