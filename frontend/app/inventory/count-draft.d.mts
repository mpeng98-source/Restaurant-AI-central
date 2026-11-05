type Entry = { quantity: string; unit: string; note: string };
type SavedLine = { inventory_item_id: string; quantity: string; unit_code: string; note: string | null };

export function countEntryChanged(entry: Entry | undefined, saved: SavedLine | undefined): boolean;
export function hasUnsavedCountEntries(entries: Record<string, Entry>, lines: SavedLine[]): boolean;
