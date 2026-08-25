/** Browser-local controls for the rendering policy applied to the next queue. */

import { api } from '../api.js';
import { h, notice, render } from '../dom.js';
import {
  loadRenderingPreference,
  normalizeRenderingPreference,
  saveRenderingPreference,
} from '../rendering.js';

const MODE_LABELS = {
  ORIGINAL: 'Original arrangement',
  PIANO_ONLY: 'Piano only',
  OVERRIDE: 'Instrument overrides',
};

/** Mount once. WebSocket/server-state updates must not rebuild this local editor. */
export function mountRenderingControls(node) {
  if (!node || node.dataset.renderingMounted === 'true') return;
  node.dataset.renderingMounted = 'true';

  let preference = loadRenderingPreference();
  let options = {
    loading: true,
    error: null,
    modes: ['ORIGINAL'],
    piano_programs: [],
    programs: [],
    percussion_channel: 9,
  };

  const rerender = () => renderRenderingControls(node, preference, options, handlers);
  const persist = (next) => {
    preference = saveRenderingPreference(next);
    rerender();
  };

  const handlers = {
    setRenderingMode(mode) {
      persist({ ...preference, mode });
    },

    setPianoProgram(program) {
      persist({ ...preference, pianoProgram: program });
    },

    addRenderingOverride() {
      const percussion = options.percussion_channel ?? 9;
      const used = new Set(preference.overrides.map((row) => row.channel));
      const channel = Array.from({ length: 16 }, (_, value) => value)
        .find((value) => value !== percussion && !used.has(value));
      if (channel === undefined) return;
      persist({
        ...preference,
        overrides: [...preference.overrides, { channel, program: 0 }],
      });
    },

    updateRenderingOverride(index, patch) {
      const overrides = preference.overrides.map((row, rowIndex) =>
        rowIndex === index ? { ...row, ...patch } : row,
      );
      persist({ ...preference, overrides });
    },

    removeRenderingOverride(index) {
      persist({
        ...preference,
        overrides: preference.overrides.filter((_, rowIndex) => rowIndex !== index),
      });
    },
  };

  rerender();
  void api.renderingOptions().then(
    (loaded) => {
      options = { ...loaded, loading: false, error: null };
      if (!options.modes.includes(preference.mode)) {
        preference = saveRenderingPreference({ ...preference, mode: 'ORIGINAL' });
      }
      rerender();
    },
    (error) => {
      // A backend without the rendering-options endpoint is treated as the old
      // compatibility path. Do not keep sending a stale non-original policy.
      preference = saveRenderingPreference({ ...preference, mode: 'ORIGINAL' });
      options = { ...options, loading: false, error };
      rerender();
    },
  );
}

function renderRenderingControls(node, preference, options, handlers) {
  preference = normalizeRenderingPreference(preference);
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
        'Using Original Arrangement until this appliance exposes the rendering vocabulary.',
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
  const used = new Set(
    preference.overrides.map((entry, rowIndex) => rowIndex === index ? -1 : entry.channel),
  );
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
