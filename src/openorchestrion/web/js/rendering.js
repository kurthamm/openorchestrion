/** Browser-local rendering preference for the next queue request. */

const STORAGE_KEY = 'oo.rendering';

export const DEFAULT_RENDERING = Object.freeze({
  mode: 'ORIGINAL',
  pianoProgram: 0,
  overrides: [],
});

function integer(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : fallback;
}

export function normalizeRenderingPreference(value) {
  const source = value && typeof value === 'object' ? value : {};
  const mode = ['ORIGINAL', 'PIANO_ONLY', 'OVERRIDE'].includes(source.mode)
    ? source.mode
    : 'ORIGINAL';
  const pianoProgram = Math.min(7, Math.max(0, integer(source.pianoProgram, 0)));
  const seen = new Set();
  const overrides = [];
  for (const row of Array.isArray(source.overrides) ? source.overrides : []) {
    const channel = integer(row?.channel, -1);
    const program = integer(row?.program, -1);
    if (channel < 0 || channel > 15 || channel === 9 || seen.has(channel)) continue;
    if (program < 0 || program > 127) continue;
    seen.add(channel);
    overrides.push({ channel, program });
  }
  return { mode, pianoProgram, overrides };
}

export function loadRenderingPreference(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem?.(STORAGE_KEY);
    return raw
      ? normalizeRenderingPreference(JSON.parse(raw))
      : { ...DEFAULT_RENDERING, overrides: [] };
  } catch {
    return { ...DEFAULT_RENDERING, overrides: [] };
  }
}

export function saveRenderingPreference(preference, storage = globalThis.localStorage) {
  const normalized = normalizeRenderingPreference(preference);
  try {
    storage?.setItem?.(STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    /* Storage denial/private mode only means the preference won't survive reload. */
  }
  return normalized;
}

/** Translate browser preference into the public queue request shape. */
export function renderingPayload(preference) {
  const normalized = normalizeRenderingPreference(preference);
  if (normalized.mode === 'ORIGINAL') return null;
  if (normalized.mode === 'PIANO_ONLY') {
    return {
      mode: 'PIANO_ONLY',
      piano_program: normalized.pianoProgram,
      program_overrides: [],
    };
  }
  if (!normalized.overrides.length) {
    throw new Error('Add at least one channel override before using Instrument overrides.');
  }
  return {
    mode: 'OVERRIDE',
    piano_program: normalized.pianoProgram,
    program_overrides: normalized.overrides.map(({ channel, program }) => ({ channel, program })),
  };
}
