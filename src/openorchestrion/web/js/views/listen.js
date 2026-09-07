/**
 * The Concierge surface — the appliance's primary question.
 *
 * Shows the interpretation before playback so the user can see what was
 * understood, surfaces `relaxations` when the selector could not honour the
 * request, and says so when an answer came from the offline interpreter.
 */

import { h, notice, render } from '../dom.js';
import { formatSeconds } from '../position.js';
import { mountRenderingControls } from './rendering.js';

/** Declarative presets mirroring config/stations.example.yaml. */
export const STATIONS = [
  { id: 'dinner', label: 'Dinner', intent: { themes: ['dinner'], moods: ['relaxed'], energy: 'low' } },
  { id: 'classical', label: 'Relaxing classical', intent: { genres: ['classical'], moods: ['relaxed'], energy: 'low' } },
  { id: 'ragtime', label: 'Ragtime', intent: { genres: ['ragtime'], energy: 'medium' } },
  { id: 'christmas', label: 'Christmas', intent: { themes: ['christmas'], familiarity: 'high' } },
  { id: 'cocktail', label: 'Cocktail hour', intent: { themes: ['cocktail'], familiarity: 'high', energy: 'medium' } },
  { id: 'two-pianos', label: 'Two pianos', intent: { performance_types: ['TWO_PIANO', 'PIANO_DUET'] } },
];

function label(value) {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

function facetHas(list, value) {
  return (list || []).some((entry) => entry.value === value);
}

/**
 * Stations offered on the Listen screen.
 *
 * The curated presets lead when the library can honour them; then one station
 * per genre and theme the catalog actually holds, most common first, so a
 * library full of baroque, film scores or video-game music gets stations for
 * those instead of a fixed six that may match nothing.
 */
export function stationsFor(facets, { genres = 10, themes = 8 } = {}) {
  if (!facets?.indexed) return STATIONS;
  const covered = new Set();
  const stations = [];
  for (const station of STATIONS) {
    const intent = station.intent;
    const ok =
      (intent.genres || []).every((g) => facetHas(facets.genres, g)) &&
      (intent.themes || []).every((t) => facetHas(facets.themes, t)) &&
      (intent.moods || []).every((m) => facetHas(facets.moods, m));
    if (!ok) continue;
    stations.push(station);
    for (const g of intent.genres || []) covered.add(`genre:${g}`);
    for (const t of intent.themes || []) covered.add(`theme:${t}`);
  }
  for (const entry of (facets.genres || []).slice(0, genres)) {
    if (covered.has(`genre:${entry.value}`)) continue;
    stations.push({ id: `genre-${entry.value}`, label: label(entry.value), intent: { genres: [entry.value] } });
  }
  for (const entry of (facets.themes || []).slice(0, themes)) {
    if (covered.has(`theme:${entry.value}`)) continue;
    stations.push({ id: `theme-${entry.value}`, label: label(entry.value), intent: { themes: [entry.value] } });
  }
  return stations.length ? stations : STATIONS;
}

export function renderStations(node, handlers, facets) {
  render(
    node,
    stationsFor(facets).map((station) =>
      h('button', {
        class: 'chip',
        type: 'button',
        onClick: () => handlers.playStation(station),
        text: station.label,
      }),
    ),
  );
  // Rendering is browser-local preference rather than server state, so mount it
  // once beside the station shortcuts instead of rebuilding it on every socket
  // state update.
  mountRenderingControls(document.getElementById('rendering-panel'));
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
 * The backend now normally supplies readable prose. This defensive recomposition
 * keeps the UI useful against older appliances or provider-specific keyword
 * fragments because the contract deliberately does not pin prose format.
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
