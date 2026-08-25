import { loadRenderingPreference, renderingPayload } from './rendering.js';

/**
 * The single seam between the UI and the backend.
 *
 * Every network call in the application goes through here, so the transport can
 * change without touching view code, and so error handling is uniform. Shapes
 * follow `docs/api-contract.md`; the authoritative schema is /openapi.json.
 */

/** An error carrying the contract's envelope, so views can switch on `code`. */
export class ApiError extends Error {
  constructor(status, body) {
    const envelope = body && body.error ? body.error : {};
    super(envelope.message || `Request failed (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.code = envelope.code || 'request_failed';
    this.detail = envelope.detail || null;
  }

  /** True when an older backend understands the request but has not built it yet. */
  get pending() {
    return this.code === 'not_implemented';
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    if (cause.name === 'AbortError') throw cause;
    throw new ApiError(0, { error: { code: 'unreachable', message: 'Cannot reach OpenOrchestrion.' } });
  }

  if (response.status === 204) return null;

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      value.forEach((entry) => search.append(key, entry));
    } else {
      search.set(key, value);
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

/** Commands are idempotent by this id, so a retry cannot double-apply a mutation. */
export function commandId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  // randomUUID is secure-context-only in some browsers; getRandomValues remains
  // available on the local HTTP appliance and gives us a valid v4-shaped UUID.
  return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c) =>
    (c ^ (globalThis.crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16),
  );
}

export const api = {
  status: () => request('/api/status'),
  devices: () => request('/api/devices'),
  renderingOptions: () => request('/api/rendering/options'),
  setup: () => request('/api/setup'),
  completeSetup: () => request('/api/setup/complete', { method: 'POST' }),
  resetSetup: () => request('/api/setup/reset', { method: 'POST' }),

  ask: ({ prompt, sessionId, currentIntent, signal, id = commandId() }) =>
    request('/api/concierge/ask', {
      method: 'POST',
      signal,
      body: {
        prompt,
        command_id: id,
        session_id: sessionId ?? null,
        current_intent: currentIntent ?? null,
      },
    }),

  stationPreview: ({ intent, seed = 0, maxTracks = 25 }) =>
    request('/api/stations/preview', {
      method: 'POST',
      body: { intent, seed, max_tracks: maxTracks },
    }),

  search: (params) => request(`/api/library/search${query(params)}`),
  libraryStats: () => request('/api/library/stats'),
  asset: (assetId) => request(`/api/library/assets/${encodeURIComponent(assetId)}`),

  setFavorite: (assetId, favorite, id = commandId()) =>
    request(`/api/library/assets/${encodeURIComponent(assetId)}/favorite`, {
      method: 'POST',
      body: { favorite, command_id: id },
    }),

  history: ({ limit = 50 } = {}) => request(`/api/history/recent${query({ limit })}`),

  queue: () => request('/api/queue'),
  replaceQueue: ({
    intent,
    assetIds = [],
    mode = 'replace',
    seed = 0,
    maxTracks = 25,
    rendering,
    id = commandId(),
  }) => {
    // Most callers intentionally omit `rendering`: the current browser-local
    // preference is applied at the transport seam, so Concierge, stations, and
    // manual Browse play all behave consistently without view-specific logic.
    const selectedRendering = rendering === undefined
      ? renderingPayload(loadRenderingPreference())
      : rendering;
    const body = {
      mode,
      intent: intent ?? null,
      asset_ids: assetIds,
      seed,
      max_tracks: maxTracks,
      command_id: id,
    };
    // Original Arrangement deliberately omits the optional field so the default
    // request stays identical to the pre-rendering browser contract.
    if (selectedRendering) body.rendering = selectedRendering;
    return request('/api/queue', { method: 'POST', body });
  },
  reorderQueue: (assetId, toIndex, id = commandId()) =>
    request('/api/queue/reorder', {
      method: 'POST',
      body: { asset_id: assetId, to_index: toIndex, command_id: id },
    }),
  removeFromQueue: (assetId, id = commandId()) =>
    request('/api/queue/remove', {
      method: 'POST',
      body: { asset_id: assetId, command_id: id },
    }),

  transport: (action, id = commandId()) =>
    request(`/api/transport/${encodeURIComponent(action)}`, {
      method: 'POST',
      body: { command_id: id },
    }),
};
