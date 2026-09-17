/** One-way copy migration; legacy values remain backups until explicit clearing. */
export const SESSION_STORAGE_KEY = "qingtu_session_id";
export const ITINERARY_STORAGE_KEY = "qingtu-itinerary-storage";
export const LEGACY_SESSION_STORAGE_KEY = "routemind_session_id";
export const LEGACY_ITINERARY_STORAGE_KEY = "routemind-itinerary-storage";

type StoragePort = Pick<Storage, "getItem" | "setItem">;
export function readBrandedStorage(storage: StoragePort, key: string, legacyKey: string): string | null {
  const current = storage.getItem(key);
  if (current !== null) return current;
  const legacy = storage.getItem(legacyKey);
  if (legacy !== null) {
    try { storage.setItem(key, legacy); } catch { /* Keep the existing session usable if storage is full. */ }
  }
  return legacy;
}
