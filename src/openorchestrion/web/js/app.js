/**
 * Application wiring.
 *
 * Holds no domain logic: it moves server state into the store, renders, and
 * turns user gestures into API commands. Selection, scoring, history and MIDI
 * timing all live in the backend (docs/api-contract.md §1).
 */

import { api, ApiError, commandId } from './api.js';
import { h } from './dom.js';
import { anchor, createTicker } from './position.js';
import { StateSocket } from './socket.js';
import { ensureSessionId, getState, setState, subscribe } from './store.js';
import { renderHealth } from './views/health.js';
import { renderAskResult, renderStations, STATIONS } from './views/listen.js';
import { renderNowPlaying, updateProgress } from './views/nowplaying.js';
import { renderFacets, renderResults } from './views/browse.js';
import { renderHistory, renderQueue } from './views/queue.js';

const nodes = {
  health: document.getElementById('health'),
  tabs: document.getElementById('tabs'),
  stations: document.getElementById('stations'),
  askForm: document.getElementById('ask-form'),
  askInput: document.getElementById('ask-input'),
  askResult: document.getElementById('ask-result'),
  surprise: document.getElementById('surprise'),
  searchForm: document.getElementById('search-form'),
  searchInput: document.getElementById('search-input'),
  searchFacets: document.getElementById('search-facets'),
  searchResults: document.getElementById('search-results'),
  queuePanel: document.getElementById('queue-panel'),
  historyPanel: document.getElementById('history-panel'),
  nowPlaying: document.getElementById('nowplaying'),
  toasts: document.getElementById('toasts'),
};

let positionAnchor = null;

// Per-frame work is a cheap in-place update, never a rebuild: replacing the
// subtree at 60fps detaches the transport buttons mid-tap. Fall back to a full
// render only if the expected structure is not there.
const ticker = createTicker(() => {
  const state = getState();
  if (!updateProgress(nodes.nowPlaying, positionAnchor, state.playback?.now_playing)) {
    renderNowPlaying(nodes.nowPlaying, state, handlers, positionAnchor);
  }
});

function toast(message, tone = 'info') {
  const node = h('div', { class: `toast toast-${tone}`, role: 'status', text: message });
  nodes.toasts.append(node);
  setTimeout(() => node.remove(), 5000);
}

/** Retain graceful behavior when controlling an older pre-#14 backend. */
function handlePlaybackCall(error, feature) {
  if (error instanceof ApiError && error.pending) {
    setState({ playbackAvailable: false, queueAvailable: false });
    toast(`${feature} is not available on this backend.`, 'warn');
    return true;
  }
  return false;
}

function pendingConfirmed(playback) {
  const pendingId = getState().pendingCommandId;
  return Boolean(pendingId && playback?.command_id === pendingId);
}

const handlers = {
  setView(view) {
    setState({ view });
    if (view === 'history') void loadHistory();
    if (view === 'queue') void loadQueue();
  },

  async ask(prompt) {
    if (!prompt.trim()) return;
    setState({ askBusy: true, askError: null });
    try {
      const result = await api.ask({
        prompt,
        sessionId: ensureSessionId(),
      });
      setState({ askBusy: false, askResult: result, lastIntent: result.intent });
    } catch (error) {
      setState({ askBusy: false, askError: error, askResult: null });
    }
  },

  async playStation(station) {
    setState({ view: 'listen', askBusy: true, askError: null });
    try {
      const preview = await api.stationPreview({ intent: station.intent });
      setState({
        askBusy: false,
        askResult: { intent: station.intent, provider: 'station', fallback_used: false, preview },
        lastIntent: station.intent,
      });
    } catch (error) {
      setState({ askBusy: false, askError: error, askResult: null });
    }
  },

  async playIntent(intent) {
    try {
      const queue = await api.replaceQueue({ intent });
      setState({ queue, queueAvailable: true, playbackAvailable: true });
      await api.transport('play');
      toast('Playing.');
    } catch (error) {
      if (handlePlaybackCall(error, 'Playing a queue')) return;
      toast(error.message, 'bad');
    }
  },

  async playAsset(assetId) {
    try {
      const queue = await api.replaceQueue({ assetIds: [assetId] });
      setState({ queue, queueAvailable: true, playbackAvailable: true });
      await api.transport('play');
    } catch (error) {
      if (handlePlaybackCall(error, 'Playing a piece')) return;
      toast(error.message, 'bad');
    }
  },

  async transport(action) {
    // Keep the id visible to both the REST call and the WebSocket path. If the
    // HTTP response is lost but the matching state delta arrives, the UI can
    // still reconcile the optimistic command instead of leaving it pending.
    const id = commandId();
    setState({ pendingTransport: action, pendingCommandId: id });
    try {
      const playback = await api.transport(action, id);
      positionAnchor = anchor(playback.position);
      setState({
        playback,
        pendingTransport: null,
        pendingCommandId: null,
        playbackAvailable: true,
      });
      syncTicker();
    } catch (error) {
      // A matching WebSocket delta may already have confirmed the command even
      // if fetch lost its response. Do not turn that success back into an error.
      if (getState().pendingCommandId !== id) return;
      setState({ pendingTransport: null, pendingCommandId: null });
      if (handlePlaybackCall(error, 'Transport control')) return;
      toast(error.message, 'bad');
    }
  },

  async search(text, facet) {
    setState({ search: { ...getState().search, loading: true, error: null, query: text, facet } });
    const params = { text: text || undefined, limit: 100 };
    if (facet) params[facet.key] = facet.value;
    try {
      const result = await api.search(params);
      setState({
        search: { ...getState().search, items: result.items, loading: false, ran: true, error: null },
      });
    } catch (error) {
      setState({ search: { ...getState().search, loading: false, ran: true, error } });
    }
  },

  searchFacet(facet) {
    void handlers.search(getState().search.query, facet);
  },

  async toggleFavorite(assetId) {
    const previous = new Set(getState().localFavorites);
    const favorites = new Set(previous);
    const next = !favorites.has(assetId);
    if (next) favorites.add(assetId);
    else favorites.delete(assetId);
    setState({ localFavorites: favorites });

    try {
      await api.setFavorite(assetId, next);
      toast(next ? 'Added to favorites.' : 'Removed from favorites.');
    } catch (error) {
      if (error instanceof ApiError && error.pending) {
        // Expected until the descriptive-metadata writer lands. Keep the choice
        // visible for this browser session and be explicit about its scope.
        setState({ favoritesPersist: false });
        toast('Kept in this browser session only — favorites are not persistent yet.', 'warn');
        return;
      }
      setState({ localFavorites: previous });
      toast(error.message, 'bad');
    }
  },

  async reorder(assetId, toIndex) {
    try {
      setState({ queue: await api.reorderQueue(assetId, toIndex) });
    } catch (error) {
      if (handlePlaybackCall(error, 'Reordering')) return;
      toast(error.message, 'bad');
    }
  },

  async removeFromQueue(assetId) {
    try {
      setState({ queue: await api.removeFromQueue(assetId) });
    } catch (error) {
      if (handlePlaybackCall(error, 'Removing from the queue')) return;
      toast(error.message, 'bad');
    }
  },
};

async function loadStatus() {
  try {
    setState({ status: await api.status() });
  } catch {
    /* health pills fall back to the connection state */
  }
}

async function loadHistory() {
  setState({ history: { ...getState().history, loading: true, error: null } });
  try {
    const result = await api.history({ limit: 50 });
    setState({ history: { items: result.items, loading: false, error: null } });
  } catch (error) {
    setState({ history: { items: [], loading: false, error } });
  }
}

async function loadQueue() {
  try {
    setState({ queue: await api.queue(), queueAvailable: true, playbackAvailable: true });
  } catch (error) {
    if (error instanceof ApiError && error.pending) {
      setState({ queueAvailable: false, playbackAvailable: false });
      return;
    }
    toast(error.message, 'bad');
  }
}

function syncTicker() {
  const rate = positionAnchor?.rate ?? 0;
  if (getState().playback?.state === 'playing' && rate > 0) ticker.start();
  else ticker.stop();
}

function applyEnvelope(envelope) {
  switch (envelope.type) {
    case 'state.snapshot': {
      const payload = envelope.payload || {};
      positionAnchor = anchor(payload.playback?.position);
      const confirmed = pendingConfirmed(payload.playback);
      setState({
        status: payload.status ?? getState().status,
        playback: payload.playback ?? getState().playback,
        queue: payload.queue ?? getState().queue,
        playbackAvailable: true,
        queueAvailable: true,
        ...(confirmed ? { pendingTransport: null, pendingCommandId: null } : {}),
      });
      syncTicker();
      break;
    }
    case 'state.playback': {
      positionAnchor = anchor(envelope.payload?.position);
      const confirmed = pendingConfirmed(envelope.payload);
      setState({
        playback: envelope.payload,
        playbackAvailable: true,
        ...(confirmed ? { pendingTransport: null, pendingCommandId: null } : {}),
      });
      syncTicker();
      break;
    }
    case 'state.queue':
      setState({ queue: envelope.payload, queueAvailable: true });
      break;
    case 'state.devices':
      setState({ status: { ...getState().status, outputs: envelope.payload } });
      break;
    case 'state.library':
      setState({ status: { ...getState().status, library: envelope.payload } });
      break;
    case 'error':
      toast(envelope.payload?.message || 'The appliance reported an error.', 'bad');
      break;
    default:
      break;
  }
}

const socket = new StateSocket({
  onMessage: applyEnvelope,
  onConnectionChange: (connection) => {
    if (connection === 'pending') {
      setState({ connection: 'pending', playbackAvailable: false, queueAvailable: false });
      return;
    }
    setState({ connection });
    if (connection === 'live') void loadStatus();
  },
});

// ---------------------------------------------------------------- rendering

subscribe((state) => {
  renderHealth(nodes.health, state);
  renderAskResult(nodes.askResult, state, handlers);
  renderFacets(nodes.searchFacets, state, handlers);
  renderResults(nodes.searchResults, state, handlers);
  renderQueue(nodes.queuePanel, state, handlers);
  renderHistory(nodes.historyPanel, state);
  renderNowPlaying(nodes.nowPlaying, state, handlers, positionAnchor);

  for (const button of nodes.tabs.querySelectorAll('.tab')) {
    const active = button.dataset.view === state.view;
    button.setAttribute('aria-current', active ? 'page' : 'false');
    button.classList.toggle('is-active', active);
  }
  for (const section of document.querySelectorAll('.view')) {
    section.hidden = section.dataset.view !== state.view;
  }
});

// ------------------------------------------------------------------ events

nodes.tabs.addEventListener('click', (event) => {
  const button = event.target.closest('.tab');
  if (button) handlers.setView(button.dataset.view);
});

nodes.askForm.addEventListener('submit', (event) => {
  event.preventDefault();
  void handlers.ask(nodes.askInput.value);
});

nodes.askInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    nodes.askForm.requestSubmit();
  }
});

nodes.surprise.addEventListener('click', () => {
  const station = STATIONS[Math.floor(Math.random() * STATIONS.length)];
  void handlers.playStation(station);
});

nodes.searchForm.addEventListener('submit', (event) => {
  event.preventDefault();
  void handlers.search(nodes.searchInput.value, getState().search.facet);
});

// ------------------------------------------------------------------- start

renderStations(nodes.stations, handlers);
ensureSessionId();
void loadStatus();
socket.connect();

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') void loadStatus();
});
