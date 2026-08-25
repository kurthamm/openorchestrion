/** Browser-local controls for the rendering policy applied to the next queue. */

import { h, notice, render } from '../dom.js';

const STORAGE_KEY = 'oo.rendering';
const MODE_LABELS = {
  ORIGINAL: 'Original arrangement',
  PIANO_ONLY: 'Piano only',
  OVERRIDE: 'Instrument overrides',
};

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
    return raw ? normalizeRenderingPreference(JSON.parse(raw)) : { ...DEFAULT_RENDERING, overrides: [] };
  } catch {
    return { ...DEFAULT_RENDERING, overrides: [] };
  }
}

export function saveRenderingPreference(preference, storage = globalThis.localStorage) {
  try {
    storage?.setItem?.(STORAGE_KEY, JSON.stringify(normalizeRenderingPreference(preference)));
  } catch {
    /* Private mode/storage denial is not a playback failure. */
  }
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

export function renderRenderingControls(node, state, handlers) {
  const preference = normalizeRenderingPreference(state.rendering);
  const options = state.renderingOptions;
  const modes = options?.modes || ['ORIGINAL'];

  const blocks = [
    h(
      'div',
      { class: 'rendering-grid' },
      field(
        'Playback sound',
        h(
          'select',
          {
            class: 'render-select',
            'aria-label': 'Playback rendering mode',
            disabled: options?.loading || false,
            onChange: (event) => handlers.setRenderingMode(event.target.value),
          },
          modes.map((mode) =>
            h('option', {
              value: mode,
              selected: preference.mode === mode,
              text: MODE_LABELS[mode] || mode,
            }),
          ),
        ),
      ),
      modeEditor(preference, options, handlers),
    ),
    h('p', {
      class: 'rendering-help',
      text: 'Applies to the next queue you create. The stored MIDI file is never changed.',
    }),
  ];

  if (options?.error) {
    blocks.push(
      notice(
        'warn',
        'Rendering options unavailable',
        'Original Arrangement still works. Reload when the appliance API is available.',
      ),
    );
  }

  render(
    node,
    h(
      'details',
      { class: 'rendering-card', open: preference.mode !== 'ORIGINAL' },
      h('summary', { text: `Sound for next queue: ${summary(preference, options)}` }),
      h('div', { class: 'rendering-body' }, blocks),
    ),
  );
}

function modeEditor(preference, options, handlers) {
  if (options?.loading) {
    return h('span', { class: 'muted rendering-loading', text: 'Loading instrument names…' });
  }

  if (preference.mode === 'PIANO_ONLY') {
    return field(
      'Piano program',
      h(
        'select',
        {
          class: 'render-select',
          'aria-label': 'Piano program',
          onChange: (event) => handlers.setPianoProgram(Number(event.target.value)),
        },
        (options?.piano_programs || []).map((program) =>
          h('option', {
            value: program.value,
            selected: preference.pianoProgram === program.value,
            text: `${program.value} · ${program.name}`,
          }),
        ),
      ),
    );
  }

  if (preference.mode !== 'OVERRIDE') {
    return h('span', {
      class: 'muted rendering-mode-note',
      text: 'Keep every source Program Change and Bank Select exactly as arranged.',
    });
  }

  const rows = preference.overrides.map((row, index) =>
    overrideRow(row, index, preference, options, handlers),
  );
  return h(
    'div',
    { class: 'render-overrides' },
    rows.length
      ? rows
      : h('p', { class: 'muted render-empty', text: 'Add a pitched MIDI channel to override.' }),
    h(
      'div',
      { class: 'render-override-actions' },
      h('button', {
        class: 'btn btn-small',
        type: 'button',
        disabled: preference.overrides.length >= 15,
        onClick: () => handlers.addRenderingOverride(),
        text: 'Add channel',
      }),
      h('span', {
        class: 'muted',
        text: 'MIDI channel 10 is percussion and cannot receive a pitched program override.',
      }),
    ),
  );
}

function overrideRow(row, index, preference, options, handlers) {
  const percussion = options?.percussion_channel ?? 9;
  const used = new Set(preference.overrides.map((entry, rowIndex) => rowIndex === index ? -1 : entry.channel));
  const channels = Array.from({ length: 16 }, (_, channel) => channel)
    .filter((channel) => channel !== percussion && !used.has(channel));

  return h(
    'div',
    { class: 'render-override-row' },
    field(
      `Channel ${row.channel + 1}`,
      h(
        'select',
        {
          class: 'render-select render-channel',
          'aria-label': `Override ${index + 1} MIDI channel`,
          onChange: (event) => handlers.updateRenderingOverride(index, { channel: Number(event.target.value) }),
        },
        channels.map((channel) =>
          h('option', {
            value: channel,
            selected: row.channel === channel,
            text: `Channel ${channel + 1}`,
          }),
        ),
      ),
    ),
    field(
      'Program',
      h(
        'select',
        {
          class: 'render-select render-program',
          'aria-label': `Override ${index + 1} General MIDI program`,
          onChange: (event) => handlers.updateRenderingOverride(index, { program: Number(event.target.value) }),
        },
        (options?.programs || []).map((program) =>
          h('option', {
            value: program.value,
            selected: row.program === program.value,
            text: `${program.value} · ${program.name}`,
          }),
        ),
      ),
    ),
    h('button', {
      class: 'btn btn-small render-remove',
      type: 'button',
      'aria-label': `Remove override for MIDI channel ${row.channel + 1}`,
      onClick: () => handlers.removeRenderingOverride(index),
      text: 'Remove',
    }),
  );
}

function field(label, control) {
  return h('label', { class: 'render-field' }, h('span', { class: 'render-label', text: label }), control);
}

function summary(preference, options) {
  if (preference.mode === 'PIANO_ONLY') {
    const program = options?.piano_programs?.find((entry) => entry.value === preference.pianoProgram);
    return program ? `Piano only · ${program.name}` : 'Piano only';
  }
  if (preference.mode === 'OVERRIDE') {
    const count = preference.overrides.length;
    return `${count} instrument override${count === 1 ? '' : 's'}`;
  }
  return 'Original arrangement';
}
