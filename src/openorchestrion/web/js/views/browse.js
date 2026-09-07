/**
 * Browse and search.
 *
 * Manual browsing matters when the Concierge is unavailable or the user wants
 * explicit control, so this path never depends on AI.
 */

import { h, notice, render } from '../dom.js';
import { formatSeconds } from '../position.js';
import { favoriteValue } from '../favorites.js';

export const FACETS = [
  { key: 'genre', value: 'classical', label: 'Classical' },
  { key: 'genre', value: 'ragtime', label: 'Ragtime' },
  { key: 'genre', value: 'jazz', label: 'Jazz' },
  { key: 'theme', value: 'christmas', label: 'Christmas' },
  { key: 'theme', value: 'dinner', label: 'Dinner' },
  { key: 'mood', value: 'relaxed', label: 'Relaxed' },
];

function label(value) {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Chips come from what the catalog actually holds (`/api/library/facets`),
 * most common first. The static FACETS list is only the fallback before that
 * answer arrives or when the library is empty.
 */
export function facetChips(facets, { genres = 12, themes = 8, moods = 6, eras = 6 } = {}) {
  if (!facets?.indexed) return FACETS;
  const chips = [];
  for (const [key, list, max] of [
    ['genre', facets.genres, genres],
    ['theme', facets.themes, themes],
    ['mood', facets.moods, moods],
  ]) {
    for (const entry of (list || []).slice(0, max)) {
      chips.push({ key, value: entry.value, label: label(entry.value), count: entry.count });
    }
  }
  return chips.length ? chips : FACETS;
}

export function renderFacets(node, state, handlers) {
  render(
    node,
    facetChips(state.facets).map((facet) => {
      const active = state.search.facet?.value === facet.value && state.search.facet?.key === facet.key;
      return h('button', {
        class: `chip${active ? ' is-active' : ''}`,
        type: 'button',
        'aria-pressed': active ? 'true' : 'false',
        onClick: () => handlers.searchFacet(active ? null : facet),
        title: facet.count ? `${facet.count} in the library` : undefined,
        text: facet.count ? `${facet.label} · ${facet.count}` : facet.label,
      });
    }),
  );
}

export function renderResults(node, state, handlers) {
  const { items, loading, ran, error } = state.search;

  if (loading) {
    render(node, h('div', { class: 'thinking' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Searching…'));
    return;
  }

  if (error) {
    render(node, notice('bad', 'Search failed', error.message));
    return;
  }

  if (!ran) {
    render(node, h('p', { class: 'muted', text: 'Search the library, or pick a filter above.' }));
    return;
  }

  if (!items.length) {
    const library = state.status?.library;
    if (library && !library.indexed) {
      render(
        node,
        notice(
          'warn',
          'No library yet',
          'Import MIDI files with openorchestrion-import-midi, then run openorchestrion-reindex.',
        ),
      );
      return;
    }
    render(node, notice('warn', 'Nothing found', 'No pieces in the library match that.'));
    return;
  }

  render(
    node,
    h(
      'ul',
      { class: 'results-list' },
      items.map((item) => assetRow(item, state, handlers)),
    ),
  );
}

function assetRow(item, state, handlers) {
  const favorite = favoriteValue(state, item);
  const unsaved = state.localFavorites.has(item.asset_id) && !state.favoritesPersist;

  return h(
    'li',
    { class: 'result' },
    h(
      'button',
      {
        class: `fav${favorite ? ' is-on' : ''}${unsaved ? ' is-unsaved' : ''}`,
        disabled: state.pendingFavorites.has(item.asset_id),
        type: 'button',
        'aria-pressed': favorite ? 'true' : 'false',
        'aria-label': favorite ? `Remove ${item.title || 'this piece'} from favorites` : `Add ${item.title || 'this piece'} to favorites`,
        title: unsaved ? 'Saved on this device only — the appliance cannot store favorites yet.' : 'Favorite',
        onClick: () => handlers.toggleFavorite(item.asset_id),
        text: favorite ? '★' : '☆',
      },
    ),
    h(
      'div',
      { class: 'result-main' },
      h('span', { class: 'result-title', text: item.title || 'Untitled' }),
      h('span', { class: 'result-sub', text: subtitle(item) }),
    ),
    h('span', { class: 'result-time', text: formatSeconds(item.duration_seconds) }),
    h('button', {
      class: 'btn btn-small',
      type: 'button',
      onClick: () => handlers.playAsset(item.asset_id),
      text: 'Play',
    }),
  );
}

function subtitle(item) {
  const parts = [item.composer || item.artist || 'Unknown'];
  if (item.performance_type) parts.push(item.performance_type.replaceAll('_', ' ').toLowerCase());
  if (item.rights_status && item.rights_status !== 'verified-open') parts.push(item.rights_status);
  return parts.join(' · ');
}
