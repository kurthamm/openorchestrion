/**
 * Client-side state.
 *
 * This is a cache of server-owned state plus purely local view state. It is
 * never the source of truth for playback, the queue, history, or setup
 * completion. Anything authoritative is replaced when the server says so.
 */

const listeners = new Set();

const initial = {
  view: 'listen',
  connection: 'connecting', // connecting | live | offline | pending
  status: null, // SystemStatus
  setup: { loading: true, data: null, error: null, autoRouted: false },
  playback: { state: 'idle', now_playing: null, position: null },
  queue: { items: [], current_index: null, total_duration_seconds: 0 },
  playbackAvailable: true,
  queueAvailable: true,
  sessionId: null,
  lastIntent: null,
  askBusy: false,
  askResult: null,
  askError: null,
  search: { query: '', items: [], loading: false, ran: false },
  history: { items: [], loading: false, error: null },
  localFavorites: new Set(),
  favoritesPersist: true,
  // Rendering is intentionally browser-local preference for the next queue.
  // The active queue/playback remain server-owned and may be replaced by a
  // different control surface at any time.
  rendering: { mode: 'ORIGINAL', pianoProgram: 0, overrides: [] },
  renderingOptions: {
    loading: true,
    error: null,
    modes: ['ORIGINAL'],
    piano_programs: [],
    programs: [],
    percussion_channel: 9,
  },
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
