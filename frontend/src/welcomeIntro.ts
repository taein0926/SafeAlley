export const WELCOME_DISMISSED_KEY = "safealley.welcome.dismissed.v1";

type SessionStore = Pick<Storage, "getItem" | "setItem">;
export function hasDismissedWelcome(storage: SessionStore | null): boolean {
  try { return storage?.getItem(WELCOME_DISMISSED_KEY) === "1"; } catch { return false; }
}
export function rememberWelcomeDismissed(storage: SessionStore | null): void {
  try { storage?.setItem(WELCOME_DISMISSED_KEY, "1"); } catch { /* Privacy mode must not block closing. */ }
}
