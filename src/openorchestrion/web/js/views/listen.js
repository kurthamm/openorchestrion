/**
 * The Concierge surface — the appliance's primary question.
 *
 * Shows the interpretation before playback so the user can see what was
 * understood, surfaces `relaxations` when the selector could not honour the
 * request, and says so when an answer came from the offline interpreter.
 */

import { h, notice, render } from '../dom.js';
import { formatSeconds } from '../position.js';

/** Declarative presets mirroring config/stations.example.yaml. */
export const STATIONS = [
  { id: 'dinner', label: 'Dinner', intent: { themes: ['dinner'], moods: ['relaxed'], energy: 'low' } },
  { id: 'classical', label: 'Relaxing classical', intent: { genres: ['classical'], moods: ['relaxed'], energy: 'low' } },
  { id: 'ragtime', label: 'Ragtime', intent: { genres: ['ragtime'], energy: 'medium' } },
  { id: 'christmas', label: 'Christmas', intent: { themes: ['christmas'], familiarity: 'high' } },
  { id: 'cocktail', label: 'Cocktail hour', intent: { themes: ['cocktail'], familiarity: 'high', energy: 'medium' } },
  { id: 'two-pianos', label: 'Two pianos', intent: { performance_types: ['TWO_PIANO', 'PIANO_DUET'] } },
];

export function renderStations(node, handlers) {
  render(
    node,
    STATIONS.map((station) =>
      h('button', {
        class: 'chip',
        type: 'button',
        onClick: () => handlers.playStation(station),
        text: station.label,
      }),
    ),
  );
}

export function renderAskResult(node, state, handlers) {
  if (state.askBusy) {
    render(node, h('div', { class: 'thinking' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Working out what to play…'));
    return;
  }

  if (state.askError) {
    render(node, notice('bad', askErrorTitle(state.askError), state.askError.message));
    return;
  }

  const result = state.askResult;
  if (!result) {
    render(node);
    return;
  }

  const blocks = [];

  if (result.fallback_used) {
    blocks.push(
      notice(
        'warn',
        'Answered offline',
        'The AI provider could not be reached, so the request was interpreted locally.',
      ),
    );
  }

  blocks.push(h('p', { class: 'interpretation', text: describe(result.intent) }));

  const preview = result.preview;
  if (!preview) {
    blocks.push(
      notice('warn', 'Nothing to play yet', 'The library has not been indexed, so no queue could be built.'),
    );
    render(node, blocks);
    return;
  }

  for (const relaxation of preview.relaxations || []) {
    blocks.push(notice('warn', 'Adjusted your request', relaxation));
  }

  if (!preview.items.length) {
    blocks.push(notice('warn', 'No matching music', 'Nothing in the library fits that request yet.'));
    render(node, blocks);
    return;
  }

  blocks.push(
    h(
      'div',
      { class: 'preview' },
      h(
        'div',
        { class: 'preview-head' },
        h('h2', { text: `${preview.items.length} pieces` }),
        h('span', { class: 'muted', text: formatSeconds(preview.total_duration_seconds) }),
        h('button', {
          class: 'btn btn-primary',
          type: 'button',
          onClick: () => handlers.playIntent(result.intent),
          text: 'Play this',
        }),
      ),
      h(
        'ol',
        { class: 'tracklist' },
        preview.items.map((item) =>
          h(
            'li',
            { class: 'track' },
            h('div', { class: 'track-main' },
              h('span', { class: 'track-title', text: item.title }),
              h('span', { class: 'track-sub', text: item.composer || 'Unknown' }),
            ),
            h('span', { class: 'track-why', text: (item.selected_for || []).join(' · ') || 'eligible' }),
            h('span', { class: 'track-time', text: formatSeconds(item.duration_seconds) }),
          ),
        ),
      ),
    ),
  );

  render(node, blocks);
}

function askErrorTitle(error) {
  switch (error.code) {
    case 'library_empty':
      return 'No music indexed yet';
    case 'unreachable':
      return 'Cannot reach the appliance';
    case 'concierge_unavailable':
      return 'The Concierge is unavailable';
    case 'intent_invalid':
      return 'That request could not be understood';
    default:
      return 'Something went wrong';
  }
}

/**
 * A short sentence describing what the appliance understood.
 *
 * docs/ux-and-control-surfaces.md asks for a readable sentence before playback
 * begins. The backend's `interpretation` is preferred when it is one; today the
 * offline interpreter emits keyword fragments ("high-familiarity, Christmas"),
 * so those are recomposed here rather than shown raw. The contract does not
 * pin the field's prose format, so this degrades instead of assuming.
 */
export function describe(intent) {
  if (!intent) return '';
  if (isSentence(intent.interpretation)) return intent.interpretation;

  const parts = [];
  if (intent.energy) parts.push(`${intent.energy}-energy`);
  if (intent.familiarity === 'high') parts.push('recognizable');
  parts.push(...(intent.moods || []));
  parts.push(...(intent.genres || []));
  parts.push(...(intent.themes || []));
  if (intent.composers?.length) parts.push(`by ${intent.composers.join(' and ')}`);
  if (intent.instrumentation?.length) parts.push(`for ${intent.instrumentation.join(' and ')}`);

  const subject = parts.length ? parts.join(' ') : 'music from your library';
  const duration = intent.duration_minutes ? ` for about ${formatDuration(intent.duration_minutes)}` : '';
  return `Playing ${subject}${duration}.`;
}

/** Treats "Playing relaxed dinner music." as prose, "dinner, low" as keywords. */
function isSentence(text) {
  if (typeof text !== 'string') return false;
  const trimmed = text.trim();
  return /^[A-Z]/.test(trimmed) && /[.!?]$/.test(trimmed) && trimmed.split(/\s+/).length >= 3;
}

function formatDuration(minutes) {
  if (minutes < 60) return `${minutes} minutes`;
  const hours = minutes / 60;
  const rounded = Number.isInteger(hours) ? hours : hours.toFixed(1);
  return `${rounded} ${Number(rounded) === 1 ? 'hour' : 'hours'}`;
}
