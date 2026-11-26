// One suggest request per chat: debounce, then run; a newer request aborts the stale one.

export const DEFAULT_DEBOUNCE_MS = 700;

export function createSuggestCoordinator({
  run, // (payload, signal) => Promise<result>
  debounceMs = DEFAULT_DEBOUNCE_MS,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
} = {}) {
  const entries = new Map(); // chatKey -> { timer, controller, settle }

  function drop(chatKey) {
    const entry = entries.get(chatKey);
    if (!entry) return;
    entries.delete(chatKey);
    if (entry.timer !== null) clearTimer(entry.timer);
    entry.controller.abort();
    entry.settle({ aborted: true });
  }

  function request(chatKey, payload, { immediate = false } = {}) {
    drop(chatKey);
    return new Promise((resolve) => {
      const entry = { timer: null, controller: new AbortController(), settle: resolve };
      entries.set(chatKey, entry);
      const start = async () => {
        entry.timer = null;
        let outcome;
        try {
          outcome = { value: await run(payload, entry.controller.signal) };
        } catch (error) {
          outcome = { error };
        }
        // A superseded entry was already settled by drop().
        if (entries.get(chatKey) !== entry) return;
        entries.delete(chatKey);
        resolve(outcome);
      };
      if (immediate || debounceMs <= 0) start();
      else entry.timer = setTimer(start, debounceMs);
    });
  }

  return {
    request,
    cancel: drop,
    cancelAllExcept(chatKey) {
      for (const key of [...entries.keys()]) if (key !== chatKey) drop(key);
    },
    pending: () => entries.size,
  };
}
