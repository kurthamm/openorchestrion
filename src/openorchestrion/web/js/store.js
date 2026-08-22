/**
 * Client-side state.
 *
 * This is a cache of server-owned state plus purely local view state. It is
 * never the source of truth for playback, the queue, or history — per
 * docs/api-contract.md the backend owns those, and anything here is replaced
 * wholesale when the server says otherwise.
 */

const listeners = new Set();

const initial = {
  view: 'listen',
  connection: 'connecting', // connecting | live | offline | pending
  status: null, // SystemStatus
  playback: { state: 'idle', now_playing: null, position: null },
  queue: { items: [], current_index: null, total_duration_seconds: 0 },
  // Playback is not implemented until issue #14; the UI must say so rather
  // than presenting dead controls as working ones.
  playbackAvailable: true,
  queueAvailable: true,
  sessionId: null,
  lastIntent: null,
  askBusy: false,
  askResult: null,
  askError: null,
  search: { query: '', items: [], loading: false, ran: false },
  history: { items: [], loading: false, error: null },
  // Favorites cannot persist until a descriptive_metadata writer exists, so
  // they are held locally and shown as unsaved rather than silently lost.
  localFavorites: new Set(),
  favoritesPersist: true,
};

let state = { ...initial };

export function getState() {
  return state;
}

export function setState(patch) {
  const next = typeof patch === 'function' ? patch(state) : patch;
  if (!next) return state;
  state = { ...state, ...next };
  for (const listener of listeners) listener(state);
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

/** Stable id for this control surface, so Concierge refinements continue. */
export function ensureSessionId() {
  if (state.sessionId) return state.sessionId;
  let id = null;
  try {
    id = localStorage.getItem('oo.session');
  } catch {
    id = null; // private mode, or storage disabled
  }
  if (!id) {
    id = globalThis.crypto?.randomUUID?.() ?? `surface-${Date.now()}`;
    try {
      localStorage.setItem('oo.session', id);
    } catch {
      /* not fatal: the conversation just won't survive a reload */
    }
  }
  setState({ sessionId: id });
  return id;
}
