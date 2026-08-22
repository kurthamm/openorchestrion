/**
 * Now Playing and transport.
 *
 * Progress is interpolated locally between server anchors (contract D1).
 * Transport buttons are optimistic: they mark themselves pending immediately so
 * a touchscreen feels responsive, then reconcile against server state (D4).
 */

import { h, render } from '../dom.js';
import { formatClock, positionAt, progressAt } from '../position.js';

const TRANSPORT = [
  { action: 'skip-back', label: 'Previous', glyph: '◀◀', hidden: true },
  { action: 'play', label: 'Play', glyph: '▶' },
  { action: 'pause', label: 'Pause', glyph: '❚❚' },
  { action: 'skip', label: 'Skip', glyph: '▶▶' },
  { action: 'stop', label: 'Stop', glyph: '■' },
];

export function renderNowPlaying(node, state, handlers, anchored) {
  const playing = state.playback?.state === 'playing';
  const track = state.playback?.now_playing || null;

  if (!state.playbackAvailable) {
    render(
      node,
      h(
        'div',
        { class: 'np np-idle' },
        h('div', { class: 'np-meta' },
          h('p', { class: 'np-title', text: 'Playback engine not built yet' }),
          h('p', {
            class: 'np-sub',
            text: 'Browsing, search, stations and the Concierge all work. Playback arrives with issue #14.',
          }),
        ),
      ),
    );
    return;
  }

  if (!track) {
    render(
      node,
      h(
        'div',
        { class: 'np np-idle' },
        h('div', { class: 'np-meta' },
          h('p', { class: 'np-title', text: 'Nothing playing' }),
          h('p', { class: 'np-sub', text: 'Ask for something, or pick a station.' }),
        ),
        transportRow(state, handlers, playing),
      ),
    );
    return;
  }

  const elapsed = positionAt(anchored);
  const fraction = progressAt(anchored);
  const durationMs = anchored?.durationMs ?? (track.duration_seconds ?? 0) * 1000;

  render(
    node,
    h(
      'div',
      { class: 'np' },
      h('div', { class: 'np-meta' },
        h('p', { class: 'np-title', text: track.title }),
        h('p', { class: 'np-sub', text: track.composer || 'Unknown' }),
      ),
      h(
        'div',
        { class: 'np-progress' },
        h('span', { class: 'np-time', text: formatClock(elapsed) }),
        h(
          'div',
          {
            class: 'bar',
            role: 'progressbar',
            'aria-label': 'Playback position',
            'aria-valuemin': '0',
            'aria-valuemax': String(Math.round(durationMs / 1000)),
            'aria-valuenow': String(Math.round(elapsed / 1000)),
            'aria-valuetext': `${formatClock(elapsed)} of ${formatClock(durationMs)}`,
          },
          h('div', {
            class: 'bar-fill',
            style: { width: fraction === null ? '0%' : `${Math.min(100, fraction * 100)}%` },
          }),
        ),
        h('span', { class: 'np-time', text: formatClock(Math.max(0, durationMs - elapsed)) }),
      ),
      transportRow(state, handlers, playing),
    ),
  );
}

function transportRow(state, handlers, playing) {
  const pending = state.pendingTransport || null;
  const buttons = TRANSPORT.filter((entry) => !entry.hidden)
    .filter((entry) => (playing ? entry.action !== 'play' : entry.action !== 'pause'))
    .map((entry) =>
      h('button', {
        class: `tbtn${entry.action === 'play' || entry.action === 'pause' ? ' tbtn-primary' : ''}${
          pending === entry.action ? ' is-pending' : ''
        }`,
        type: 'button',
        'aria-label': entry.label,
        title: entry.label,
        onClick: () => handlers.transport(entry.action),
        text: entry.glyph,
      }),
    );

  buttons.push(
    h('button', {
      class: 'tbtn tbtn-panic',
      type: 'button',
      'aria-label': 'Panic: all notes off',
      title: 'Panic — silence every device immediately',
      onClick: () => handlers.transport('panic'),
      text: '⨯',
    }),
  );

  return h('div', { class: 'np-transport', role: 'group', 'aria-label': 'Transport controls' }, buttons);
}
