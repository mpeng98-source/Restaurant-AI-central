type Entry = { quantity: string; unit: string; note: string; photo?: string };
type SavedLine = { inventory_item_id: string; quantity: string; unit_code: string; note: string | null; photo_object_key?: string | null };

export function countEntryChanged(entry: Entry | undefined, saved: SavedLine | undefined): boolean;
export function hasUnsavedCountEntries(entries: Record<string, Entry>, lines: SavedLine[]): boolean;
